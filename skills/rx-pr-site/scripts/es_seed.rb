if ARGV.include?("--help")
  puts <<~USAGE
    usage: [ID_FLOOR=900000000] [MAX_ROWS=1000] [EXTRA_USER_IDS=a,b] [ORG_PROVIDER_ORG_IDS=a,b] bin/rails runner es_seed.rb
    Inline Searchkick reindex of organizations/providers/users rows with id >= ID_FLOOR (refuses a model
    with more than MAX_ROWS such rows), then the organization_providers fan-out for each canonical bz org
    in ORG_PROVIDER_ORG_IDS (~27k docs, 3-5 min per org; refuses ids below the floor). Never a full
    reindex. Retry once on Net::ReadTimeout. Prints one JSON line.
  USAGE
  exit 0
end

floor = Integer(ENV.fetch("ID_FLOOR", "900000000"))
max_rows = Integer(ENV.fetch("MAX_ROWS", "1000"))
extra_user_ids = ENV.fetch("EXTRA_USER_IDS", "").split(",").map(&:to_i)
Rails.application.eager_load! if Searchkick.models.empty?
report = { id_floor: floor, searchkick_models: Searchkick.models.map(&:name).sort, seeded: {}, missing_index: [], errors: [] }
started = Process.clock_gettime(Process::CLOCK_MONOTONIC)
Searchkick.models.each do |model|
  next unless %w[organizations providers users].include?(model.table_name)

  scope = model.where(id: floor..)
  scope = scope.or(model.where(id: extra_user_ids)) if model.table_name == "users" && extra_user_ids.any?
  ids = scope.pluck(:id)
  next if ids.empty?

  if ids.size > max_rows
    report[:errors] << "#{model.name}: #{ids.size} rows in range, refused"
    next
  end

  unless model.search_index.exists?
    report[:missing_index] << model.name
    next
  end
  count = 0
  scope.find_each do |record|
    next if record.respond_to?(:should_index?) && !record.should_index?

    record.reindex(mode: :inline)
    count += 1
  rescue StandardError => e
    report[:errors] << "#{model.name}##{record.id}: #{e.class}: #{e.message[0, 160]}"
  end
  model.search_index.refresh
  report[:seeded][model.name] = count
end
op_started = Process.clock_gettime(Process::CLOCK_MONOTONIC)
ENV.fetch("ORG_PROVIDER_ORG_IDS", "").split(",").map(&:to_i).each do |org_id|
  raise "refusing org #{org_id}: below #{floor}" if org_id < floor

  org = Pg::Organization.find(org_id)
  org.organization_providers.search_import.reindex
  report[:seeded]["Pg::OrganizationProvider(org #{org_id})"] = org.organization_providers.count
rescue StandardError => e
  report[:errors] << "OrganizationProvider org #{org_id}: #{e.class}: #{e.message[0, 160]}"
end
report[:org_provider_seconds] = (Process.clock_gettime(Process::CLOCK_MONOTONIC) - op_started).round(1)
Pg::OrganizationProvider.search_index.refresh
report[:seconds] = (Process.clock_gettime(Process::CLOCK_MONOTONIC) - started).round(1)
puts JSON.generate(report)

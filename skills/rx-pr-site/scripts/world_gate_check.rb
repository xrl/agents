if ARGV.include?("--help") || ENV["PAIRS"].to_s.empty?
  puts <<~USAGE
    usage: PAIRS=<user_id>:<org_id>[,<user_id>:<org_id>...] bin/rails runner world_gate_check.rb
    Read-only RevealBi::AuthorizationService gate matrix: for each pair, membership, tier, surfaces
    and the can_* gates. Runs in a READ ONLY transaction that is rolled back. Prints ids, never emails.
  USAGE
  exit(ARGV.include?("--help") ? 0 : 2)
end

pairs = ENV.fetch("PAIRS").split(",").map { |p| p.split(":").map { |x| Integer(x) } }
gates = %i[can_view? can_view_storefront? can_view_storefront_reports? can_author?]
out = []
ActiveRecord::Base.transaction do
  ActiveRecord::Base.connection.execute("SET TRANSACTION READ ONLY")
  pairs.each do |uid, oid|
    user = Pg::User.find(uid)
    org = Pg::Organization.find(oid)
    s = RevealBi::AuthorizationService.new(user: user, organization: org)
    row = { user_id: uid, org: oid, member: user.organizations.exists?(id: oid) }
    row[:tier] = s.tier if s.respond_to?(:tier)
    row[:surfaces] = s.surfaces.sort if s.respond_to?(:surfaces)
    gates.each { |g| row[g.to_s.delete_suffix("?")] = s.public_send(g) if s.respond_to?(g) }
    row[:org_reveal_bi_storefront] = org.has_feature?(:reveal_bi_storefront) if org.respond_to?(:has_feature?)
    out << row
  end
  raise ActiveRecord::Rollback
end
puts JSON.generate(out)

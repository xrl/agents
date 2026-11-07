require "net/http"

if ARGV.empty? || ARGV.include?("--help")
  puts <<~USAGE
    usage: rails_runner.sh <N> publish_dashboards.rb --with <dir> -- <dir basename>
    <dir> (relative to this script) holds plan.json and <id>.rdash files from build_rdash.py. Mints a Backoffice admin
    TokenService token for STAFF_EMAIL (default bz-bo-staff@bronzezilla.example), then for each plan
    entry PUTs /dashboards/<id> and PATCHes /dashboards/<id>/publish on the in-cluster rx-reveal.
    Writes dashboards on the PR site: journal it. Prints one JSON line per run.
  USAGE
  exit(ARGV.include?("--help") ? 0 : 2)
end

dir = File.expand_path(ARGV.fetch(0), __dir__)
plan = JSON.parse(File.read(File.join(dir, "plan.json")))
staff = Pg::User.find_by!(email: ENV.fetch("STAFF_EMAIL", "bz-bo-staff@bronzezilla.example"))
backoffice = Pg::Organization.backoffice_organization
token = RevealBi::TokenService.new(
  user: staff, organization: backoffice, tier: :admin,
  market_side: RevealBi::MarketSide::ORGANIZATION, surfaces: ["backoffice"]
)
base = URI.parse(token.server_url)

call = lambda do |klass, path, body: nil, content_type: nil|
  uri = URI.join(base.to_s.end_with?("/") ? base.to_s : "#{base}/", path.delete_prefix("/"))
  http = Net::HTTP.new(uri.host, uri.port)
  http.use_ssl = uri.scheme == "https"
  http.open_timeout = 5
  http.read_timeout = 60
  req = klass.new(uri.request_uri)
  req["Authorization"] = "Bearer #{token.auth_token}"
  req["Accept"] = "application/json"
  if body
    req["Content-Type"] = content_type
    req.body = body
  end
  http.request(req)
end

out = { server: "#{base.scheme}://#{base.host}:#{base.port}", results: [] }
plan.each do |entry|
  row = { name: entry["name"], id: entry["id"] }
  rdash = File.binread(File.join(dir, "#{entry['id']}.rdash"))
  res = call.call(Net::HTTP::Put, "/dashboards/#{entry['id']}", body: rdash, content_type: "application/octet-stream")
  row[:save] = res.code
  row[:save_body] = res.body.to_s[0, 200] unless res.is_a?(Net::HTTPSuccess)
  if res.is_a?(Net::HTTPSuccess)
    pp = ActiveSupport::HashWithIndifferentAccess.new(entry["publish"])
    error = pp[:visibility] == "draft" ? nil : RevealBi::PublishingService.validate(pp)
    if error
      row[:publish_error] = error
    else
      body = RevealBi::PublishingService.build_body(pp)
      pres = call.call(Net::HTTP::Patch, "/dashboards/#{entry['id']}/publish", body: body.to_json, content_type: "application/json")
      row[:publish] = pres.code
      if pres.is_a?(Net::HTTPSuccess)
        state = JSON.parse(pres.body)
        row[:state] = state.slice("all_organizations", "all_providers", "organization_ids", "provider_ids", "excluded_organization_ids", "excluded_provider_ids")
        row[:state]["user_grants"] = state["user_grants"]
      else
        row[:publish_body] = pres.body.to_s[0, 200]
      end
    end
  end
  out[:results] << row
end
puts JSON.generate(out)

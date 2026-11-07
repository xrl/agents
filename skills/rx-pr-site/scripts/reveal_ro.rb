if ARGV.empty? || ARGV.include?("--help")
  puts <<~USAGE
    usage: rails_runner.sh <N> reveal_ro.rb --reveal-creds --with <query.sql> -- <query.sql basename>
    Reads the reveal schema, which the Rails role cannot ("permission denied for schema reveal").
    stdin carries the rx-reveal pod's own connection (5 lines: host, port, db, user, password; rails_runner.sh
    --reveal-creds pipes them pod to pod, never through a file). The query runs under
    default_transaction_read_only plus BEGIN READ ONLY and is rolled back; only SELECT/WITH is accepted.
    Prints {columns, n, rows} with at most MAX_ROWS (default 200) rows. Select ids, never emails or names.
  USAGE
  exit(ARGV.include?("--help") ? 0 : 2)
end

sql = File.read(File.expand_path(ARGV.fetch(0), __dir__)).strip.sub(/;\s*\z/, "")
abort("refusing: only one SELECT or WITH statement") unless sql.match?(/\A(select|with)\b/i) && !sql.include?(";")

host, port, db, user, password = $stdin.read.split("\n")
abort("expected 5 credential lines on stdin") if password.to_s.empty?
max_rows = Integer(ENV.fetch("MAX_ROWS", "200"))
conn = PG.connect(host: host, port: port.to_i, dbname: db, user: user, password: password, sslmode: "require")
begin
  conn.exec("SET default_transaction_read_only = on")
  conn.exec("BEGIN READ ONLY")
  res = conn.exec(sql)
  puts JSON.generate(columns: res.fields, n: res.ntuples, rows: res.values.first(max_rows))
ensure
  conn.exec("ROLLBACK") rescue nil
  conn.close
end

import argparse
import copy
import io
import json
import sys
import uuid
import zipfile
from pathlib import Path

DEFAULT_MAP = {
    'organizations': {'1001': 900000001, '1002': 900000002, '1003': 900000003, '1004': 900000004, '1005': 900000005},
    'providers': {'1001': 900000001, '1002': 900000002, '1003': 900000003},
    'users': {},
}

HELP = '''Turn bronzezilla dashboards exported from a local Reveal DB into .rdash files plus a plan.json
that publish_dashboards.rb reads. Input is JSON lines, one dashboard per line, with keys
id, name, description, content (the Dashboard.json object), all_organizations, all_providers,
organization_ids, provider_ids, user_grants [{user_id, canonical_organization_id}],
excluded_organization_ids, excluded_provider_ids. Org, provider and user ids are remapped to the
PR site's >=900M bz ids; the data source is repointed from the local schema to the clone's.
A grant whose id has no mapping stops the build.'''


def remap(table, kind, old):
    try:
        return table[kind][str(old)]
    except KeyError:
        sys.exit(f'no {kind} mapping for id {old}; pass --id-map')


def write_rdash(out_dir, dash_id, content):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('Dashboard.json', json.dumps(content))
    (out_dir / f'{dash_id}.rdash').write_bytes(buf.getvalue())


def publish_body(d, ids):
    granted = d['all_organizations'] or d['all_providers'] or d['organization_ids'] or d['provider_ids'] or d['user_grants']
    return {
        'visibility': 'published' if granted else 'draft',
        'all_organizations': '1' if d['all_organizations'] else '0',
        'all_providers': '1' if d['all_providers'] else '0',
        'organization_ids': [str(remap(ids, 'organizations', i)) for i in d['organization_ids']],
        'provider_ids': [str(remap(ids, 'providers', i)) for i in d['provider_ids']],
        'user_ids': [f"{remap(ids, 'users', g['user_id'])}:{remap(ids, 'organizations', g['canonical_organization_id'])}" for g in d['user_grants']],
        'excluded_organization_ids': [str(remap(ids, 'organizations', i)) for i in (d['excluded_organization_ids'] or [])],
        'excluded_provider_ids': [str(remap(ids, 'providers', i)) for i in (d['excluded_provider_ids'] or [])],
    }


def stress_dashboard(grid, cols, n, title, orgs):
    stress = copy.deepcopy(grid)
    sid = str(uuid.uuid5(uuid.NAMESPACE_URL, f'rx-pr-site/{title}'))
    stress['Title'] = title
    w = stress['Widgets'][0]
    w['Id'] = str(uuid.uuid5(uuid.NAMESPACE_URL, f'rx-pr-site/{title}/widget'))
    w['Title'] = f'{n} columns'
    names = {f['FieldName'] for f in w['DataSpec']['Fields']}
    pick = [c for c in cols if c in names][:n]
    if len(pick) != n:
        sys.exit(f'only {len(pick)} of {n} columns exist on the grid widget')
    w['VisualizationDataSpec']['Columns'] = [{'Axis': {}, '_type': 'TabularColumnSpecType', 'IsHidden': False, 'FieldName': c} for c in pick]
    publish = {'visibility': 'published', 'all_organizations': '0', 'all_providers': '0', 'organization_ids': orgs,
               'provider_ids': [], 'user_ids': [], 'excluded_organization_ids': [], 'excluded_provider_ids': []}
    return sid, stress, {'id': sid, 'name': title, 'description': f'Export stress: one grid, {n} columns', 'publish': publish}


def main():
    p = argparse.ArgumentParser(description=HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('src', type=Path, help='dashboards JSON lines')
    p.add_argument('out_dir', type=Path)
    p.add_argument('--id-map', type=Path, help='JSON {organizations:{old:new}, providers:{...}, users:{...}}; default maps orgs 1001-1005 and providers 1001-1003 to 900000001+')
    p.add_argument('--from-table-prefix', default='rx_development.transform.')
    p.add_argument('--to-table-prefix', default='sci_rx_production.bronzezilla_transform.')
    p.add_argument('--from-schema', default='transform')
    p.add_argument('--to-schema', default='bronzezilla_transform')
    p.add_argument('--stress-grid', help='name of the grid dashboard to clone into a wide export-stress dashboard')
    p.add_argument('--stress-columns-file', type=Path, help='lines "<table>|<column>" (psql -At over information_schema.columns)')
    p.add_argument('--stress-table', default='reveal_marketplace_report')
    p.add_argument('--stress-n', type=int, default=37)
    p.add_argument('--stress-title', default='BZ-EXPORT-STRESS-37')
    p.add_argument('--stress-orgs', default='900000001,900000004')
    a = p.parse_args()

    ids = json.loads(a.id_map.read_text()) if a.id_map else DEFAULT_MAP
    for k in ('organizations', 'providers', 'users'):
        ids.setdefault(k, {})
    a.out_dir.mkdir(parents=True, exist_ok=True)

    def repoint(content):
        s = json.dumps(content)
        s = s.replace(f'"{a.from_table_prefix}', f'"{a.to_table_prefix}')
        s = s.replace(f'"Schema": "{a.from_schema}"', f'"Schema": "{a.to_schema}"')
        return json.loads(s)

    plan, grid = [], None
    for line in a.src.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        content = repoint(d['content'])
        if d['name'] == a.stress_grid:
            grid = content
        write_rdash(a.out_dir, d['id'], content)
        plan.append({'id': d['id'], 'name': d['name'], 'description': d['description'], 'publish': publish_body(d, ids)})

    if a.stress_grid:
        if grid is None or a.stress_columns_file is None:
            sys.exit('--stress-grid needs a matching dashboard and --stress-columns-file')
        prefix = f'{a.stress_table}|'
        cols = [l.split('|')[1].strip() for l in a.stress_columns_file.read_text().splitlines() if l.startswith(prefix)]
        sid, stress, entry = stress_dashboard(grid, cols, a.stress_n, a.stress_title, a.stress_orgs.split(','))
        write_rdash(a.out_dir, sid, stress)
        plan.append(entry)

    (a.out_dir / 'plan.json').write_text(json.dumps(plan, indent=1))
    print(json.dumps([[e['name'], e['publish']['visibility']] for e in plan]))


if __name__ == '__main__':
    main()

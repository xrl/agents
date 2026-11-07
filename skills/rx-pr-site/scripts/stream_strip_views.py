import argparse
import re
import sys

HDR = re.compile(r'^-- (?:Data for )?Name: (?P<name>[^;]+); Type: (?P<type>[^;]+); Schema: (?P<schema>[^;]+);')


def is_view(m):
    return m['type'] == 'VIEW' or (m['type'] == 'COMMENT' and m['name'].startswith('VIEW '))


def strip(fin, fout, from_schema, to_schema):
    state = {'skip': False, 'in_copy': False, 'pending_dash': False, 'dropped': 0, 'public_refs': 0}

    def emit(line):
        if not state['in_copy']:
            line = line.replace(from_schema, to_schema)
            if 'public.' in line:
                state['public_refs'] += 1
        fout.write(line)

    for line in fin:
        if state['in_copy']:
            if not state['skip']:
                fout.write(line)
            if line == '\\.\n':
                state['in_copy'] = False
            continue
        if state['pending_dash']:
            state['pending_dash'] = False
            m = HDR.match(line)
            if m:
                state['skip'] = is_view(m)
                if state['skip']:
                    state['dropped'] += 1
            if not state['skip']:
                emit('--\n')
        if line == '--\n':
            state['pending_dash'] = True
            continue
        if not state['skip']:
            emit(line)
        if line.startswith('COPY '):
            state['in_copy'] = True
    if state['pending_dash'] and not state['skip']:
        emit('--\n')
    return state


def main():
    p = argparse.ArgumentParser(description='Streaming view stripper for dumps too big for memory (1.77 GB in one pass). '
                                'Drops VIEW chunks, renames the schema outside COPY data, and counts public. references '
                                'left in kept DDL. Exit 1 if any remain.')
    p.add_argument('src')
    p.add_argument('dst')
    p.add_argument('--from-schema', default='bronzezilla_transform')
    p.add_argument('--to-schema', required=True, help='schema name to load into, e.g. bronzezilla_stress')
    a = p.parse_args()
    with open(a.src, encoding='utf-8', newline='') as fin, open(a.dst, 'w', encoding='utf-8', newline='') as fout:
        s = strip(fin, fout, a.from_schema, a.to_schema)
    print(f"dropped {s['dropped']} views, public refs kept {s['public_refs']}")
    sys.exit(1 if s['public_refs'] else 0)


if __name__ == '__main__':
    main()

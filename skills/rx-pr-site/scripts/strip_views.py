import argparse
import re
import sys

HDR = re.compile(r'^-- (?:Data for )?Name: (?P<name>[^;]+); Type: (?P<type>[^;]+); Schema: (?P<schema>[^;]+);')


def is_view(m):
    return m['type'] == 'VIEW' or (m['type'] == 'COMMENT' and m['name'].startswith('VIEW '))


def main():
    p = argparse.ArgumentParser(description='Drop every VIEW (and view COMMENT) chunk from a plain pg_dump that fits in memory. '
                                'Refuses to write if a kept chunk still references a dropped view or any public.<relation>, '
                                'because on a prod clone a view over public.* hands real rows to whoever reads the schema.')
    p.add_argument('src')
    p.add_argument('dst')
    p.add_argument('--schema', default='bronzezilla_transform', help='schema the dump creates (default bronzezilla_transform)')
    a = p.parse_args()

    with open(a.src, encoding='utf-8') as f:
        lines = f.readlines()
    chunks = [[]]
    for line in lines:
        if HDR.match(line) and chunks[-1] and chunks[-1][-1] == '--\n':
            chunks[-1].pop()
            chunks.append(['--\n'])
        chunks[-1].append(line)
    dropped, kept = [], []
    for c in chunks:
        m = next((HDR.match(l) for l in c[:3] if HDR.match(l)), None)
        if m and is_view(m):
            dropped.append(m['name'])
            continue
        kept.append(c)
    out = ''.join(''.join(c) for c in kept)
    for n in dropped:
        base = n.split(' ')[-1]
        if re.search(re.escape(a.schema) + r'\.' + re.escape(base) + r'\b', out):
            sys.exit(f'dangling reference to dropped view {base}')
    if re.search(r'\bpublic\.', out):
        sys.exit('public. reference remains')
    with open(a.dst, 'w', encoding='utf-8') as f:
        f.write(out)
    print(f'dropped {len(dropped)} views, kept {len(kept)} chunks')


if __name__ == '__main__':
    main()

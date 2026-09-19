"""Separate AI triggers from normal builds; only registered textbook changes."""
import os
import subprocess
from review import ROOT, config, run
import json


def affected(paths, lessons):
    result = []
    for lesson in lessons:
        source = lesson['source_path']
        watched = {source}
        if source.startswith('content/'):
            folder = source.rsplit('/', 1)[0]
            watched |= {folder + '/content.md', folder + '/meta.json', folder + '/anchors.json'}
        if set(paths) & watched:
            result.append(lesson['lesson_id'])
    return result


if __name__ == '__main__':
    lessons = config(ROOT)['lessons']
    force = os.environ.get('REVIEW_ALL') == 'true'
    requested = os.environ.get('REVIEW_LESSON', '').strip()
    if requested and requested not in {l['lesson_id'] for l in lessons}:
        raise SystemExit('Unknown lesson_id')
    if os.environ.get('REVIEW_EVENT') == 'workflow_dispatch':
        selected = [requested] if requested else None
        force = force or bool(requested)
    else:
        before = os.environ.get('REVIEW_BEFORE', '')
        if not before or set(before) == {'0'}:
            selected = None
        else:
            paths = subprocess.check_output(['git', 'diff', '--name-only', '-z', before, 'HEAD'], cwd=ROOT).decode('utf-8').split('\0')
            selected = affected(paths, lessons)
    result = run(ROOT, ROOT / '_site', generate=True, only=selected, force=force)
    print(json.dumps(result, ensure_ascii=False, indent=2))

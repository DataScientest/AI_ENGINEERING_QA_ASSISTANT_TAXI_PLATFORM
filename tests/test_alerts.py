import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

RULES = Path('services/prometheus/alert_rules.yml')


def all_alerts():
    return [r for g in yaml.safe_load(RULES.read_text())['groups'] for r in g['rules'] if 'alert' in r]


def test_every_alert_has_duration_severity_message_and_action():
    for rule in all_alerts():
        name = rule['alert']
        assert rule.get('for'), f'{name}: missing for:'
        assert rule['labels']['severity'] in {'page', 'ticket'}, name
        assert rule['labels'].get('layer'), name
        assert rule['annotations']['summary'] and rule['annotations']['description'], name
        assert rule['annotations']['action'], f'{name}: no associated action'
        anchor = rule['annotations']['runbook_url'].split('#')[1]
        assert f'## {name}'.lower() in Path('docs/RUNBOOKS.md').read_text().lower(), f'{name}: no runbook section {anchor}'

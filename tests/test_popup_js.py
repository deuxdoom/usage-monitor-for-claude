"""
Popup JS Tests
===============

Behavior tests for popup.js DOM update logic, executed with Node.js
against a minimal DOM stub.  Skipped when Node.js is not installed -
the app itself never needs Node; it is only used as a test runner
for the popup's JavaScript.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_POPUP_JS = Path(__file__).parent.parent / 'usage_monitor_for_claude' / 'popup' / 'popup.js'

_NODE = shutil.which('node')

# Minimal DOM stub covering exactly the APIs the bar create/update path uses.
_DOM_STUB = r'''
class StubElement {
    constructor(tag) {
        this.tagName = tag;
        this.className = '';
        this.textContent = '';
        this.title = '';
        this.style = {};
        this.dataset = {};
        this.children = [];
        this.parentNode = null;
        const element = this;
        this.classList = {
            toggle(name, force) {
                const classes = element._classSet();
                const on = force === undefined ? !classes.has(name) : !!force;
                if (on) classes.add(name); else classes.delete(name);
                element.className = [...classes].join(' ');
                return on;
            },
            add(name) { const classes = element._classSet(); classes.add(name); element.className = [...classes].join(' '); },
            remove(name) { const classes = element._classSet(); classes.delete(name); element.className = [...classes].join(' '); },
            contains(name) { return element._classSet().has(name); },
        };
    }
    _classSet() { return new Set(this.className.split(/\s+/).filter(Boolean)); }
    appendChild(node) { node.parentNode = this; this.children.push(node); return node; }
    append(...nodes) { for (const node of nodes) this.appendChild(node); }
    replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
    remove() {
        if (this.parentNode) {
            const index = this.parentNode.children.indexOf(this);
            if (index >= 0) this.parentNode.children.splice(index, 1);
            this.parentNode = null;
        }
    }
    matches(selector) { return selector.startsWith('.') && this._classSet().has(selector.slice(1)); }
    querySelector(selector) {
        for (const child of this.children) {
            if (child.matches(selector)) return child;
            const nested = child.querySelector(selector);
            if (nested) return nested;
        }
        return null;
    }
    querySelectorAll(selector) {
        const found = [];
        for (const child of this.children) {
            if (child.matches(selector)) found.push(child);
            found.push(...child.querySelectorAll(selector));
        }
        return found;
    }
}

globalThis.document = {
    createElement: (tag) => new StubElement(tag),
    body: new StubElement('body'),
};
globalThis.ResizeObserver = class { constructor() {} observe() {} };
globalThis.requestAnimationFrame = (callback) => callback();
'''

_SCENARIO_PRELUDE = r'''
els = { usageBars: document.createElement('div') };

function makeEntry(overrides) {
    return Object.assign({
        key: 'five_hour', label: '5h', pct_text: '0%', fill_pct: 0.0,
        warn: false, dividers: [], marker_rel: null, reset_text: '',
    }, overrides);
}
'''


def _run_scenario(scenario: str) -> dict:
    """Execute the DOM stub + popup.js + scenario with Node and parse its JSON output."""
    script = _DOM_STUB + _POPUP_JS.read_text(encoding='utf-8') + _SCENARIO_PRELUDE + scenario
    with TemporaryDirectory() as tmp:
        script_path = Path(tmp) / 'scenario.js'
        script_path.write_text(script, encoding='utf-8')
        proc = subprocess.run([_NODE, str(script_path)], capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise AssertionError(f'Node scenario failed:\n{proc.stderr}')
    return json.loads(proc.stdout)


@unittest.skipUnless(_NODE, 'Node.js not available')
class TestAccountRow(unittest.TestCase):
    """Tests for renderAccountRow in popup.js - the name/email toggle."""

    _PRELUDE = r"""
const labelEl = document.createElement('dt');
labelEl.id = 'labelEmail';
document.getElementById = (id) => (id === 'labelEmail' ? labelEl : null);
els = { emailValue: document.createElement('dd'), emailRow: document.createElement('div') };
els.emailRow.style = {};
translations = { email: 'Email', name: 'Name', reveal_email: 'show', hide_email: 'hide' };
"""

    _EPILOGUE = """
console.log(JSON.stringify({
    label: labelEl.textContent,
    value: els.emailValue.textContent,
    className: els.emailValue.className,
    title: els.emailValue.title,
    display: els.emailRow.style.display,
}));
"""

    def _render(self, profile, revealed=False):
        state = f'emailRevealed = {"true" if revealed else "false"};\nrenderAccountRow({profile});\n'
        return _run_scenario(self._PRELUDE + state + self._EPILOGUE)

    def test_name_shown_by_default(self):
        """With a name available the email is not on screen until asked for."""
        out = self._render("{ email: 'max@clau.de', name: 'Max Clau' }")
        self.assertEqual(out['value'], 'Max Clau')
        self.assertEqual(out['label'], 'Name')
        self.assertNotIn('masked', out['className'])
        self.assertEqual(out['title'], 'show')

    def test_email_shown_when_revealed(self):
        out = self._render("{ email: 'max@clau.de', name: 'Max Clau' }", revealed=True)
        self.assertEqual(out['value'], 'max@clau.de')
        self.assertEqual(out['label'], 'Email')
        self.assertEqual(out['title'], 'hide')

    def test_email_blurred_without_a_name(self):
        """No name to show instead, so the address itself is rendered blurred."""
        out = self._render("{ email: 'max@clau.de', name: '' }")
        self.assertEqual(out['value'], 'max@clau.de')
        self.assertEqual(out['label'], 'Email')
        self.assertIn('masked', out['className'])

    def test_blur_cleared_when_revealed(self):
        out = self._render("{ email: 'max@clau.de', name: '' }", revealed=True)
        self.assertNotIn('masked', out['className'])
        self.assertIn('toggleable', out['className'])

    def test_name_without_email_is_not_toggleable(self):
        """Nothing is hidden, so the row must not offer a pointless click."""
        out = self._render("{ email: '', name: 'Max Clau' }")
        self.assertNotIn('toggleable', out['className'])
        self.assertEqual(out['title'], '')

    def test_row_hidden_when_profile_has_neither(self):
        out = self._render("{ email: '', name: '' }")
        self.assertEqual(out['display'], 'none')


@unittest.skipUnless(_NODE, 'Node.js not available')
class TestStatusText(unittest.TestCase):
    """Tests for tickStatusText in popup.js."""

    _PRELUDE = r"""
els = {
    statusText: document.createElement('span'),
    usageSection: document.createElement('div'),
    extraSection: document.createElement('div'),
};
translations = {
    status_updated_s: 'updated {s}s ago',
    status_updated: 'updated {duration} ago',
    status_next_update: 'next in {duration}',
    status_refreshing: 'refreshing',
    duration_hm: '{h}h {m}m',
    duration_m: '{m}m',
    duration_s: '{s}s',
};
const NOW = Date.now() / 1000;
"""

    _EPILOGUE = "\ntickStatusText();\nconsole.log(JSON.stringify({ text: els.statusText.textContent }));\n"

    def _status(self, state):
        return _run_scenario(self._PRELUDE + state + self._EPILOGUE)['text']

    def test_countdown_shown_within_the_first_minute(self):
        """The next-update countdown does not wait for the elapsed half to reach 60s."""
        state = "statusState = { lastSuccessTime: NOW - 5, nextPollTime: NOW + 115 };"
        self.assertEqual(self._status(state), "updated 5s ago \u00b7 next in 2m")

    def test_countdown_shown_after_a_minute(self):
        state = "statusState = { lastSuccessTime: NOW - 90, nextPollTime: NOW + 90 };"
        self.assertEqual(self._status(state), "updated 1m ago \u00b7 next in 2m")

    def test_countdown_under_a_minute_shown_in_seconds(self):
        state = "statusState = { lastSuccessTime: NOW - 10, nextPollTime: NOW + 30 };"
        self.assertEqual(self._status(state), "updated 10s ago \u00b7 next in 30s")

    def test_refreshing_replaces_the_countdown(self):
        state = "statusState = { lastSuccessTime: NOW - 10, nextPollTime: NOW + 30, refreshing: true };"
        self.assertEqual(self._status(state), "updated 10s ago \u00b7 refreshing")

    def test_no_countdown_without_a_scheduled_poll(self):
        state = "statusState = { lastSuccessTime: NOW - 10 };"
        self.assertEqual(self._status(state), "updated 10s ago")


@unittest.skipUnless(_NODE, 'Node.js not available')
class TestUsageBarUpdates(unittest.TestCase):
    """Tests for updateUsageBars/updateBarElement in popup.js."""

    def test_changed_field_set_with_equal_count_updates_labels(self):
        """When the set of quota fields changes but the count stays the same
        (e.g. an account switch between plans), the bars must not show the new
        percentages under the old labels."""
        result = _run_scenario('''
updateUsageBars([
    makeEntry({ key: 'five_hour', label: '5h', pct_text: '10%' }),
    makeEntry({ key: 'seven_day', label: '7d', pct_text: '20%' }),
]);
updateUsageBars([
    makeEntry({ key: 'five_hour', label: '5h', pct_text: '30%' }),
    makeEntry({ key: 'seven_day_opus', label: '7d Opus', pct_text: '99%' }),
]);
console.log(JSON.stringify(els.usageBars.children.map((bar) => ({
    label: bar.children[0].children[0].textContent,
    pct: bar.querySelector('.bar-pct').textContent,
}))));
''')
        self.assertEqual(result, [
            {'label': '5h', 'pct': '30%'},
            {'label': '7d Opus', 'pct': '99%'},
        ])

    def test_marker_and_divider_positions_stable_across_update(self):
        """The 2 px marker/divider elements are centered with a -1px correction
        on create; an in-place update must use the identical expression, or the
        elements shift by 1 px after the first data update."""
        result = _run_scenario('''
const fields = { key: 'five_hour', label: '5h', marker_rel: 0.5, dividers: [0.25] };
updateUsageBars([makeEntry(Object.assign({ pct_text: '10%' }, fields))]);
const container = els.usageBars.children[0].querySelector('.bar-container');
const before = {
    marker: container.querySelector('.bar-marker').style.left,
    divider: container.querySelector('.bar-divider').style.left,
};
updateUsageBars([makeEntry(Object.assign({ pct_text: '11%' }, fields))]);
const after = {
    marker: container.querySelector('.bar-marker').style.left,
    divider: container.querySelector('.bar-divider').style.left,
};
console.log(JSON.stringify({ before, after }));
''')
        self.assertEqual(result['after'], result['before'])

    def test_unchanged_field_set_updates_in_place(self):
        """With an unchanged field set, bars are updated in place (no rebuild)."""
        result = _run_scenario('''
updateUsageBars([makeEntry({ key: 'five_hour', label: '5h', pct_text: '10%' })]);
const barBefore = els.usageBars.children[0];
updateUsageBars([makeEntry({ key: 'five_hour', label: '5h', pct_text: '50%', fill_pct: 0.5 })]);
console.log(JSON.stringify({
    sameElement: els.usageBars.children[0] === barBefore,
    pct: els.usageBars.children[0].querySelector('.bar-pct').textContent,
    fillWidth: els.usageBars.children[0].querySelector('.bar-fill').style.width,
}));
''')
        self.assertEqual(result, {'sameElement': True, 'pct': '50%', 'fillWidth': '50%'})


if __name__ == '__main__':
    unittest.main()

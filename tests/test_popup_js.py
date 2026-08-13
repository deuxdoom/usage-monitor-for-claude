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
        this._text = '';
        this.title = '';
        this.style = {};
        this.dataset = {};
        this.attributes = {};
        this.children = [];
        this.parentNode = null;
        this._listeners = {};
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
    // Mirrors real DOM: reading textContent recurses into children, and
    // writing it clears them and stores a single flat string - so a
    // container built entirely from appendChild() calls (e.g. the session
    // detail panel) reports its full text the same way a leaf element with
    // a directly assigned string does.
    get textContent() {
        return this.children.length === 0 ? this._text : this.children.map((c) => c.textContent).join('');
    }
    set textContent(value) {
        this._text = value;
        this.children = [];
    }
    _classSet() { return new Set(this.className.split(/\s+/).filter(Boolean)); }
    appendChild(node) { node.parentNode = this; this.children.push(node); return node; }
    append(...nodes) { for (const node of nodes) this.appendChild(node); }
    replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
    insertBefore(node, refNode) {
        node.parentNode = this;
        if (refNode == null) { this.children.push(node); return node; }
        const index = this.children.indexOf(refNode);
        this.children.splice(index === -1 ? this.children.length : index, 0, node);
        return node;
    }
    setAttribute(name, value) { this.attributes[name] = String(value); }
    getAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attributes, name) ? this.attributes[name] : null; }
    addEventListener(type, handler) { (this._listeners[type] ??= []).push(handler); }
    dispatchEvent(type, eventObj) { for (const handler of this._listeners[type] || []) handler(eventObj || {}); }
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
globalThis.window = globalThis;
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


@unittest.skipUnless(_NODE, 'Node.js not available')
class TestUsageDetailToggle(unittest.TestCase):
    """Tests for the click-to-expand session_detail panel on five_hour/seven_day bars."""

    _TRANSLATIONS = r"""
translations = {
    detail_tokens: 'Tokens', detail_messages: 'Messages',
    detail_estimated: '(~{total} total, est.)', detail_models: 'Model usage',
    detail_loading: 'Loading...', detail_unavailable: 'Unavailable',
    detail_no_usage: 'No Claude Code activity', detail_source: 'From local logs',
};
"""

    def _scenario(self, body: str) -> dict:
        return _run_scenario(self._TRANSLATIONS + body)

    def test_detail_field_is_clickable(self):
        result = self._scenario('''
const bar = createBarElement(makeEntry({ key: 'five_hour' }));
console.log(JSON.stringify({
    className: bar.className,
    role: bar.getAttribute('role'),
    tabindex: bar.getAttribute('tabindex'),
    ariaExpanded: bar.getAttribute('aria-expanded'),
}));
''')
        self.assertIn('detail-toggleable', result['className'])
        self.assertEqual(result['role'], 'button')
        self.assertEqual(result['tabindex'], '0')
        self.assertEqual(result['ariaExpanded'], 'false')

    def test_non_detail_field_is_not_clickable(self):
        """A model-scoped or unlabeled quota has no local-log equivalent to show."""
        result = self._scenario('''
const bar = createBarElement(makeEntry({ key: 'seven_day_opus' }));
console.log(JSON.stringify({
    className: bar.className,
    role: bar.getAttribute('role'),
}));
''')
        self.assertNotIn('detail-toggleable', result['className'])
        self.assertIsNone(result['role'])

    def test_click_shows_loading_state_immediately(self):
        result = self._scenario('''
window.pywebview = { api: { session_detail: () => new Promise(() => {}) } };
const bar = createBarElement(makeEntry({ key: 'five_hour' }));
bar.dispatchEvent('click');
console.log(JSON.stringify({
    text: bar.querySelector('.usage-detail').textContent,
    expanded: bar.classList.contains('expanded'),
    ariaExpanded: bar.getAttribute('aria-expanded'),
}));
''')
        self.assertEqual(result['text'], 'Loading...')
        self.assertTrue(result['expanded'])
        self.assertEqual(result['ariaExpanded'], 'true')

    def test_click_renders_tokens_and_messages(self):
        result = self._scenario('''
window.pywebview = { api: { session_detail: () => Promise.resolve({
    unavailable: false, tokens: '353,830', messages: '1,033', estimated_total: null, models: [],
}) } };
const bar = createBarElement(makeEntry({ key: 'five_hour' }));
bar.dispatchEvent('click');
Promise.resolve().then(() => {
    const panel = bar.querySelector('.usage-detail');
    const counts = panel.querySelector('.detail-counts');
    console.log(JSON.stringify({
        tokenLine: counts.children[0].textContent,
        estimated: counts.children[0].querySelector('.detail-estimated'),
        messageLine: counts.children[1].textContent,
    }));
});
''')
        self.assertEqual(result['tokenLine'], 'Tokens 353,830')
        self.assertIsNone(result['estimated'])
        self.assertEqual(result['messageLine'], 'Messages 1,033')

    def test_estimated_total_appended_when_present(self):
        result = self._scenario('''
window.pywebview = { api: { session_detail: () => Promise.resolve({
    unavailable: false, tokens: '353,830', messages: '1,033', estimated_total: '853,171', models: [],
}) } };
const bar = createBarElement(makeEntry({ key: 'five_hour' }));
bar.dispatchEvent('click');
Promise.resolve().then(() => {
    const est = bar.querySelector('.detail-estimated');
    console.log(JSON.stringify({ text: est ? est.textContent : null }));
});
''')
        self.assertEqual(result['text'], ' (~853,171 total, est.)')

    def test_click_renders_model_breakdown(self):
        result = self._scenario('''
window.pywebview = { api: { session_detail: () => Promise.resolve({
    unavailable: false, tokens: '353,830', messages: '1,033', estimated_total: null,
    models: [
        { model: 'claude-sonnet-4-6', tokens: '341,802', pct: '96.6' },
        { model: 'claude-opus-4-8', tokens: '12,028', pct: '3.4' },
    ],
}) } };
const bar = createBarElement(makeEntry({ key: 'seven_day' }));
bar.dispatchEvent('click');
Promise.resolve().then(() => {
    const rows = bar.querySelectorAll('.detail-model-row');
    console.log(JSON.stringify({
        heading: bar.querySelector('.detail-models-heading').textContent,
        rows: rows.map((row) => ({
            name: row.querySelector('.detail-model-name').textContent,
            width: row.querySelector('.detail-model-bar-fill').style.width,
            pct: row.querySelector('.detail-model-pct').textContent,
        })),
    }));
});
''')
        self.assertEqual(result['heading'], 'Model usage')
        self.assertEqual(result['rows'], [
            {'name': 'claude-sonnet-4-6', 'width': '96.6%', 'pct': '96.6%'},
            {'name': 'claude-opus-4-8', 'width': '3.4%', 'pct': '3.4%'},
        ])

    def test_source_note_always_shown_with_data(self):
        """The panel must name its source: local logs miss web/app usage entirely."""
        result = self._scenario('''
window.pywebview = { api: { session_detail: () => Promise.resolve({
    unavailable: false, tokens: '100', messages: '1', estimated_total: null, models: [],
}) } };
const bar = createBarElement(makeEntry({ key: 'five_hour' }));
bar.dispatchEvent('click');
Promise.resolve().then(() => {
    console.log(JSON.stringify({ note: bar.querySelector('.detail-source').textContent }));
});
''')
        self.assertEqual(result['note'], 'From local logs')

    def test_source_note_shown_for_empty_period_too(self):
        """An empty period is exactly when the source caveat matters most."""
        result = self._scenario('''
window.pywebview = { api: { session_detail: () => Promise.resolve({
    unavailable: false, tokens: '0', messages: '0', estimated_total: null, models: [],
}) } };
const bar = createBarElement(makeEntry({ key: 'five_hour' }));
bar.dispatchEvent('click');
Promise.resolve().then(() => {
    console.log(JSON.stringify({ note: bar.querySelector('.detail-source').textContent }));
});
''')
        self.assertEqual(result['note'], 'From local logs')

    def test_zero_usage_shows_no_usage_message(self):
        result = self._scenario('''
window.pywebview = { api: { session_detail: () => Promise.resolve({
    unavailable: false, tokens: '0', messages: '0', estimated_total: null, models: [],
}) } };
const bar = createBarElement(makeEntry({ key: 'five_hour' }));
bar.dispatchEvent('click');
Promise.resolve().then(() => {
    console.log(JSON.stringify({ text: bar.querySelector('.usage-detail').textContent }));
});
''')
        self.assertEqual(result['text'], 'No Claude Code activityFrom local logs')

    def test_unavailable_result_shows_error_state(self):
        result = self._scenario('''
window.pywebview = { api: { session_detail: () => Promise.resolve({
    unavailable: true, tokens: null, messages: null, estimated_total: null, models: [],
}) } };
const bar = createBarElement(makeEntry({ key: 'five_hour' }));
bar.dispatchEvent('click');
Promise.resolve().then(() => {
    const panel = bar.querySelector('.usage-detail');
    console.log(JSON.stringify({ text: panel.textContent, className: panel.className }));
});
''')
        self.assertEqual(result['text'], 'Unavailable')
        self.assertIn('error', result['className'])

    def test_rejected_promise_shows_error_state(self):
        result = self._scenario('''
window.pywebview = { api: { session_detail: () => Promise.reject(new Error('bridge error')) } };
const bar = createBarElement(makeEntry({ key: 'five_hour' }));
bar.dispatchEvent('click');
Promise.resolve().then(() => Promise.resolve()).then(() => {
    const panel = bar.querySelector('.usage-detail');
    console.log(JSON.stringify({ text: panel.textContent, className: panel.className }));
});
''')
        self.assertEqual(result['text'], 'Unavailable')
        self.assertIn('error', result['className'])

    def test_missing_bridge_shows_unavailable_without_calling_anything(self):
        """dev-preview or a pywebview build without the API must not throw."""
        result = self._scenario('''
const bar = createBarElement(makeEntry({ key: 'five_hour' }));
bar.dispatchEvent('click');
console.log(JSON.stringify({ text: bar.querySelector('.usage-detail').textContent }));
''')
        self.assertEqual(result['text'], 'Unavailable')

    def test_second_click_collapses_and_removes_panel(self):
        result = self._scenario('''
window.pywebview = { api: { session_detail: () => Promise.resolve({
    unavailable: false, tokens: '100', messages: '1', estimated_total: null, models: [],
}) } };
const bar = createBarElement(makeEntry({ key: 'five_hour' }));
bar.dispatchEvent('click');
Promise.resolve().then(() => {
    bar.dispatchEvent('click');
    console.log(JSON.stringify({
        panel: bar.querySelector('.usage-detail'),
        expanded: bar.classList.contains('expanded'),
        ariaExpanded: bar.getAttribute('aria-expanded'),
    }));
});
''')
        self.assertIsNone(result['panel'])
        self.assertFalse(result['expanded'])
        self.assertEqual(result['ariaExpanded'], 'false')

    def test_enter_key_toggles_like_click(self):
        result = self._scenario('''
window.pywebview = { api: { session_detail: () => new Promise(() => {}) } };
const bar = createBarElement(makeEntry({ key: 'five_hour' }));
let defaultPrevented = false;
bar.dispatchEvent('keydown', { key: 'Enter', preventDefault: () => { defaultPrevented = true; } });
console.log(JSON.stringify({ expanded: bar.classList.contains('expanded'), defaultPrevented }));
''')
        self.assertTrue(result['expanded'])
        self.assertTrue(result['defaultPrevented'])

    def test_space_key_toggles_like_click(self):
        result = self._scenario('''
window.pywebview = { api: { session_detail: () => new Promise(() => {}) } };
const bar = createBarElement(makeEntry({ key: 'five_hour' }));
bar.dispatchEvent('keydown', { key: ' ', preventDefault: () => {} });
console.log(JSON.stringify({ expanded: bar.classList.contains('expanded') }));
''')
        self.assertTrue(result['expanded'])

    def test_other_key_does_not_toggle(self):
        result = self._scenario('''
const bar = createBarElement(makeEntry({ key: 'five_hour' }));
bar.dispatchEvent('keydown', { key: 'Tab', preventDefault: () => {} });
console.log(JSON.stringify({ expanded: bar.classList.contains('expanded') }));
''')
        self.assertFalse(result['expanded'])

    def test_expanded_panel_survives_full_bar_rebuild(self):
        """updateUsageBars rebuilds bars wholesale when the field set changes;
        an open panel must re-open on the new element rather than vanishing."""
        result = self._scenario('''
window.pywebview = { api: { session_detail: () => Promise.resolve({
    unavailable: false, tokens: '100', messages: '1', estimated_total: null, models: [],
}) } };
updateUsageBars([makeEntry({ key: 'five_hour' })]);
els.usageBars.children[0].dispatchEvent('click');
Promise.resolve().then(() => {
    // Field-set change forces the rebuild path in updateUsageBars.
    updateUsageBars([makeEntry({ key: 'five_hour' }), makeEntry({ key: 'seven_day' })]);
    Promise.resolve().then(() => {
        const bar = els.usageBars.children[0];
        console.log(JSON.stringify({
            expanded: bar.classList.contains('expanded'),
            text: bar.querySelector('.usage-detail')?.textContent ?? null,
        }));
    });
});
''')
        self.assertTrue(result['expanded'])
        self.assertEqual(result['text'], 'Tokens 100Messages 1From local logs')

    def test_reset_text_created_after_panel_stays_below_it(self):
        """A reset-text that appears while the panel is already open (e.g. a
        just-touched five_hour bar gets its first reset time) must not be
        inserted below the detail panel."""
        result = self._scenario('''
window.pywebview = { api: { session_detail: () => Promise.resolve({
    unavailable: false, tokens: '100', messages: '1', estimated_total: null, models: [],
}) } };
updateUsageBars([makeEntry({ key: 'five_hour', reset_text: '' })]);
els.usageBars.children[0].dispatchEvent('click');
Promise.resolve().then(() => {
    updateUsageBars([makeEntry({ key: 'five_hour', reset_text: 'Resets in 5h' })]);
    const bar = els.usageBars.children[0];
    console.log(JSON.stringify(bar.children.map((c) => c.className)));
});
''')
        self.assertEqual(result, ['bar-header', 'bar-container', 'reset-text', 'usage-detail'])


if __name__ == '__main__':
    unittest.main()

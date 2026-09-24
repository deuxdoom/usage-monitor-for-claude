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

_POPUP_JS = Path(__file__).parent.parent / 'ai_agents_usage_monitor' / 'popup' / 'popup.js'

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
        # Node writes UTF-8 whatever the console code page is, and the popup
        # renders characters outside it - the em dash standing in for a
        # quota with no data, for one - so the encoding is named rather
        # than left to the locale, where it decodes as mojibake or raises.
        proc = subprocess.run(
            [_NODE, str(script_path)], capture_output=True, text=True, encoding='utf-8', timeout=30,
        )
    if proc.returncode != 0:
        raise AssertionError(f'Node scenario failed:\n{proc.stderr}')
    return json.loads(proc.stdout)


@unittest.skipUnless(_NODE, 'Node.js not available')
class TestBarWindows(unittest.TestCase):
    """Which two quotas the bar view shows, chosen by window length."""

    _PRELUDE = """
els = { barCards: document.createElement('div') };
"""

    def _windows(self, entries: str) -> dict:
        scenario = f"""
const [session, weekly] = barWindows({entries});
console.log(JSON.stringify({{
    session: session ? session.key : null,
    weekly: weekly ? weekly.key : null,
}}));
"""
        return _run_scenario(self._PRELUDE + scenario)

    def test_the_shortest_window_is_the_session(self):
        out = self._windows(
            "[makeEntry({key: 'seven_day', period_seconds: 604800}),"
            " makeEntry({key: 'five_hour', period_seconds: 18000})]"
        )
        self.assertEqual(out['session'], 'five_hour')
        self.assertEqual(out['weekly'], 'seven_day')

    def test_a_model_scoped_limit_does_not_displace_the_weekly_one(self):
        """Same-length windows keep the order they arrived in, which puts the
        plain weekly quota ahead of a model-scoped one."""
        out = self._windows(
            "[makeEntry({key: 'five_hour', period_seconds: 18000}),"
            " makeEntry({key: 'seven_day', period_seconds: 604800}),"
            " makeEntry({key: 'seven_day_opus', period_seconds: 604800})]"
        )
        self.assertEqual(out['weekly'], 'seven_day')

    def test_a_single_quota_leaves_the_second_row_empty(self):
        out = self._windows("[makeEntry({key: 'five_hour', period_seconds: 18000})]")
        self.assertEqual(out['session'], 'five_hour')
        self.assertIsNone(out['weekly'])

    def test_no_data_leaves_both_rows_empty(self):
        out = self._windows('[]')
        self.assertIsNone(out['session'])
        self.assertIsNone(out['weekly'])

    def test_an_entry_without_a_window_length_is_skipped(self):
        """A quota whose period cannot be derived has no place on a timed row."""
        out = self._windows(
            "[makeEntry({key: 'mystery', period_seconds: null}),"
            " makeEntry({key: 'five_hour', period_seconds: 18000})]"
        )
        self.assertEqual(out['session'], 'five_hour')
        self.assertIsNone(out['weekly'])


@unittest.skipUnless(_NODE, 'Node.js not available')
class TestBarClock(unittest.TestCase):
    def test_separator_blinks_each_second_without_changing_the_time_text(self):
        for language in ('en', 'ko', 'ja'):
            for time_format in ('12h', '24h'):
                with self.subTest(language=language, time_format=time_format):
                    result = _run_scenario('''
els = {clockDate: document.createElement('div'), clockTime: document.createElement('div')};
const RealDate = Date;
let instant = new RealDate(2026, 8, 12, 23, 59, 58).getTime();
Date = class extends RealDate {constructor(...args) {super(...(args.length ? args : [instant]));}};
''' + f'setupClock({json.dumps(language)}, {json.dumps(time_format)});\n' + '''
const ticks = [];
for (let i = 0; i < 3; i++) {
    renderClock();
    const separator = els.clockTime.querySelector('.clock-separator');
    ticks.push({text: els.clockTime.textContent, label: els.clockTime.getAttribute('aria-label'),
        separator: separator.textContent, off: separator.classList.contains('off'), date: els.clockDate.textContent});
    instant += 1000;
}
console.log(JSON.stringify(ticks));
''')
                    self.assertEqual([tick['off'] for tick in result], [False, True, False])
                    self.assertEqual([tick['separator'] for tick in result], [':', ':', ':'])
                    self.assertEqual(result[0]['text'], result[1]['text'])
                    self.assertEqual(result[0]['label'], result[1]['label'])
                    self.assertIn('11:59' if time_format == '12h' else '23:59', result[0]['text'])
                    self.assertRegex(result[2]['text'], r'12:00' if time_format == '12h' else r'(?:00|24):00')
                    self.assertNotEqual(result[0]['date'], result[2]['date'])


@unittest.skipUnless(_NODE, 'Node.js not available')
class TestBarView(unittest.TestCase):
    """The single-row view: two rows per agent, and the used/remaining toggle."""

    _PRELUDE = """
els = {
    barCards: document.createElement('div'),
    clockDate: document.createElement('div'),
    clockTime: document.createElement('div'),
};
translations = { bar_used: '{label} {pct} used', bar_left: '{label} {pct} left' };
setupClock('en', '24h');
lastData = { usage: [
    makeEntry({key: 'five_hour', label: '5h', period_seconds: 18000, pct_text: '42%', left_text: '58%', fill_pct: 0.42, marker_rel: 0.3}),
    makeEntry({key: 'seven_day', label: '7d', period_seconds: 604800, pct_text: '65%', left_text: '35%', fill_pct: 0.65, warn: true}),
] };
codexData = { account: { usage: [
    makeEntry({key: 'codex_hour', label: '5h', period_seconds: 18000, pct_text: '12%', left_text: '88%', fill_pct: 0.12}),
] } };
"""

    _EPILOGUE = """
const cards = els.barCards.children;
console.log(JSON.stringify({
    names: cards.map((card) => card.querySelector('.bar-card-name').textContent),
    rows: cards.map((card) => card.querySelectorAll('.bar-row').map((row) => ({
        pct: row.querySelector('.bar-row-pct').textContent,
        width: row.querySelector('.bar-fill').style.width,
        classes: row.className,
        warn: row.querySelector('.bar-fill').className,
        title: row.title,
    }))),
    clock: els.clockTime.textContent !== '' && els.clockDate.textContent !== '',
}));
"""

    def _render(self, extra: str = '') -> dict:
        return _run_scenario(self._PRELUDE + 'renderBarView();\n' + extra + self._EPILOGUE)

    def test_one_card_per_agent(self):
        out = self._render()
        self.assertEqual(out['names'], ['CLAUDE', 'CODEX'])

    def test_each_card_carries_a_session_row_and_a_weekly_row(self):
        out = self._render()
        self.assertEqual([len(rows) for rows in out['rows']], [2, 2])
        self.assertIn('weekly', out['rows'][0][1]['classes'])
        self.assertNotIn('weekly', out['rows'][0][0]['classes'])

    def test_percentages_read_as_used_by_default(self):
        out = self._render()
        self.assertEqual([row['pct'] for row in out['rows'][0]], ['42%', '65%'])

    def test_a_missing_quota_shows_a_dash_and_keeps_its_row(self):
        """The row holds the card's height so the window does not resize later."""
        out = self._render()
        codex_weekly = out['rows'][1][1]
        self.assertEqual(codex_weekly['pct'], '\u2014')
        self.assertIn('empty', codex_weekly['classes'])

    def test_the_fill_measures_what_has_been_used(self):
        out = self._render()
        self.assertEqual(out['rows'][0][0]['width'], '42%')

    def test_an_over_pace_bar_stays_marked_in_either_row(self):
        """The warning has to outrank the color the weekly row would otherwise get."""
        out = self._render()
        self.assertIn('warn', out['rows'][0][1]['warn'])

    def test_the_clock_is_rendered(self):
        out = self._render()
        self.assertTrue(out['clock'])

    def test_clicking_a_card_switches_to_remaining(self):
        out = self._render('els.barCards.children[0].dispatchEvent("click");\n')
        self.assertEqual([row['pct'] for row in out['rows'][0]], ['58%', '35%'])

    def test_the_switch_applies_to_every_card_at_once(self):
        """One number reading as used beside another reading as remaining would
        be worse than either alone."""
        out = self._render('els.barCards.children[0].dispatchEvent("click");\n')
        self.assertEqual(out['rows'][1][0]['pct'], '88%')

    def test_the_fill_still_measures_use_after_the_switch(self):
        """It is read against the elapsed-time marker, which inverting would strand."""
        out = self._render('els.barCards.children[0].dispatchEvent("click");\n')
        self.assertEqual(out['rows'][0][0]['width'], '42%')

    def test_clicking_twice_returns_to_used(self):
        out = self._render(
            'els.barCards.children[0].dispatchEvent("click");\n'
            'els.barCards.children[0].dispatchEvent("click");\n'
        )
        self.assertEqual(out['rows'][0][0]['pct'], '42%')

    def test_each_row_says_which_quota_and_which_reading_it_is(self):
        """The rows carry no labels, so the tooltip is where that is said."""
        out = self._render()
        self.assertEqual(out['rows'][0][0]['title'], '5h 42% used')

    def test_the_tooltip_follows_the_switch(self):
        out = self._render('els.barCards.children[0].dispatchEvent("click");\n')
        self.assertEqual(out['rows'][0][0]['title'], '5h 58% left')


@unittest.skipUnless(_NODE, 'Node.js not available')
class TestBarUpdates(unittest.TestCase):
    def test_toggle_and_refresh_keep_the_card_and_fill_elements(self):
        result = _run_scenario(TestBarView._PRELUDE + '''
renderBarView();
const card = els.barCards.children[0], fill = card.querySelector('.bar-fill');
card.dispatchEvent('keydown', {key: 'Enter', preventDefault() {}});
lastData.usage[0] = makeEntry({period_seconds: 18000, label: '5h', pct_text: '50%', left_text: '50%', fill_pct: 0.5});
renderBarView();
const refreshed = {sameCard: card === els.barCards.children[0], sameFill: fill === card.querySelector('.bar-fill'),
    width: fill.style.width, pressed: card.getAttribute('aria-pressed'), label: card.getAttribute('aria-label')};
card.dispatchEvent('keydown', {key: ' ', preventDefault() {}});
console.log(JSON.stringify({refreshed, pressed: card.getAttribute('aria-pressed')}));
''')
        self.assertTrue(result['refreshed']['sameCard'])
        self.assertTrue(result['refreshed']['sameFill'])
        self.assertEqual(result['refreshed']['width'], '50%')
        self.assertEqual(result['refreshed']['pressed'], 'true')
        self.assertIn('5h 50% left', result['refreshed']['label'])
        self.assertEqual(result['pressed'], 'false')

    def test_missing_quota_clears_its_fill_marker_and_tooltip(self):
        result = _run_scenario(TestBarView._PRELUDE + '''
renderBarView();
const row = els.barCards.children[0].querySelector('.bar-row');
lastData.usage = [];
renderBarView();
console.log(JSON.stringify({width: row.querySelector('.bar-fill').style.width,
    marker: row.querySelector('.bar-marker'), dividers: row.querySelectorAll('.bar-divider').length,
    title: row.title, empty: row.classList.contains('empty')}));
''')
        self.assertEqual(result, {'width': '0%', 'marker': None, 'dividers': 0, 'title': '', 'empty': True})

    def test_failed_reads_mark_cached_values_and_recovery_clears_the_warning(self):
        result = _run_scenario(TestBarView._PRELUDE + '''
lastData.status = {error: 'Claude error'};
codexReadError = 'Codex error';
renderBarView();
const errors = Array.from(els.barCards.children, card => ({stale: card.classList.contains('stale'), title: card.title}));
lastData.status.error = null;
codexReadError = null;
renderBarView();
console.log(JSON.stringify({errors, recovered: Array.from(els.barCards.children, card => !card.classList.contains('stale') && card.title === '')}));
''')
        self.assertEqual(result['errors'], [{'stale': True, 'title': 'Claude error'}, {'stale': True, 'title': 'Codex error'}])
        self.assertEqual(result['recovered'], [True, True])


@unittest.skipUnless(_NODE, 'Node.js not available')
class TestPopupDrag(unittest.TestCase):
    def test_clock_drag_needs_no_pin_in_bar_mode(self):
        for mode, pinned, expected in [('bar', False, 1), ('detail', False, 0), ('detail', True, 1)]:
            with self.subTest(mode=mode, pinned=pinned):
                result = _run_scenario('''
const header = document.createElement('header'), clock = document.createElement('div');
const listeners = {};
document.querySelector = () => header;
document.getElementById = () => clock;
document.addEventListener = (name, handler) => {listeners[name] = handler;};
for (const handle of [header, clock]) {
    handle.setPointerCapture = () => {};
    handle.hasPointerCapture = () => false;
}
let begins = 0, moves = 0, ends = 0;
globalThis.pywebview = {api: {
    begin_drag: async () => {begins++; return true;},
    drag: async () => {moves++;}, end_drag: async () => {ends++;},
}};
''' + f'viewMode = {json.dumps(mode)}; popupPinned = {json.dumps(pinned)};\n' + '''
setupPopupDrag();
clock.dispatchEvent('pointerdown', {button: 0, pointerId: 1, target: {closest: () => null}, preventDefault() {}});
setImmediate(() => {
    listeners.pointermove({pointerId: 1, buttons: 1});
    listeners.pointerup({pointerId: 1});
    console.log(JSON.stringify({begins, moves, ends}));
});
''')
                self.assertEqual(result, {'begins': expected, 'moves': expected, 'ends': expected})


@unittest.skipUnless(_NODE, 'Node.js not available')
class TestViewSwitch(unittest.TestCase):
    def test_bar_controls_return_to_detail_and_close_through_the_bridge(self):
        result = _run_scenario('''
const nodes = {};
document.getElementById = id => nodes[id] || (nodes[id] = document.createElement('button'));
translations = {view_bar: 'Bar', view_detail: 'Detail', close_popup: 'Close'};
let modes = [], closes = 0;
switchViewMode = mode => modes.push(mode);
globalThis.pywebview = {api: {close: () => {closes++;}}};
setupViewButtons();
setupCloseButtons();
nodes.barExpandBtn.dispatchEvent('click');
nodes.barCloseBtn.dispatchEvent('click');
console.log(JSON.stringify({modes, closes, expand: nodes.barExpandBtn.getAttribute('aria-label'), close: nodes.barCloseBtn.getAttribute('aria-label')}));
''')
        self.assertEqual(result, {'modes': ['detail'], 'closes': 1, 'expand': 'Detail', 'close': 'Close'})

    def test_waits_for_the_host_and_ignores_duplicate_clicks(self):
        result = _run_scenario('''
let resolveSwitch, calls = 0, renders = [];
globalThis.pywebview = {api: {set_view_mode: () => {calls++; return new Promise(resolve => {resolveSwitch = resolve;});}}};
applyViewMode = mode => {viewMode = mode; renders.push(mode);};
const pending = switchViewMode('bar');
switchViewMode('bar');
const before = {calls, renders: [...renders]};
resolveSwitch(true);
pending.then(() => console.log(JSON.stringify({before, renders, busy: viewSwitchBusy})));
''')
        self.assertEqual(result, {'before': {'calls': 1, 'renders': []}, 'renders': ['bar'], 'busy': False})

    def test_failed_bridge_preserves_the_layout_and_allows_a_retry(self):
        result = _run_scenario('''
globalThis.pywebview = {api: {set_view_mode: async () => {throw new Error('closed');}}};
applyViewMode = mode => {viewMode = mode;};
switchViewMode('bar').then(async () => {
    const failed = {mode: viewMode, busy: viewSwitchBusy};
    pywebview.api.set_view_mode = async () => true;
    await switchViewMode('bar');
    console.log(JSON.stringify({failed, mode: viewMode}));
});
''')
        self.assertEqual(result, {'failed': {'mode': 'detail', 'busy': False}, 'mode': 'bar'})


@unittest.skipUnless(_NODE, 'Node.js not available')
class TestCodexNeeded(unittest.TestCase):
    """Who keeps the Codex reads running."""

    def _needed(self, view: str, provider: str) -> bool:
        scenario = f"""
viewMode = '{view}';
selectedProvider = '{provider}';
console.log(JSON.stringify({{needed: codexNeeded()}}));
"""
        return _run_scenario(scenario)['needed']

    def test_the_codex_tab_needs_them(self):
        self.assertTrue(self._needed('detail', 'codex'))

    def test_the_bar_needs_them_whichever_tab_is_selected(self):
        """The bar shows both agents, so the Claude tab being selected is irrelevant."""
        self.assertTrue(self._needed('bar', 'claude'))

    def test_the_claude_detail_view_does_not(self):
        self.assertFalse(self._needed('detail', 'claude'))


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
    duration_ms: '{m}m {s}s',
    duration_s: '{s}s',
};
const NOW = Date.now() / 1000;
"""

    _EPILOGUE = "\ntickStatusText();\nconsole.log(JSON.stringify({ text: els.statusText.textContent }));\n"

    def _status(self, state):
        return _run_scenario(self._PRELUDE + state + self._EPILOGUE)['text']

    def test_countdown_is_the_whole_status_line(self):
        """Only the countdown is shown - the elapsed half is not appended."""
        state = "statusState = { lastSuccessTime: NOW - 5, nextPollTime: NOW + 115 };"
        self.assertRegex(self._status(state), r"^next in 1m \d{1,2}s$")

    def test_countdown_ignores_how_long_ago_the_fetch_was(self):
        """A fetch minutes old still shows only the countdown, not its own age."""
        state = "statusState = { lastSuccessTime: NOW - 90, nextPollTime: NOW + 90 };"
        self.assertRegex(self._status(state), r"^next in 1m \d{1,2}s$")

    def test_countdown_under_a_minute_shown_in_seconds(self):
        state = "statusState = { lastSuccessTime: NOW - 10, nextPollTime: NOW + 30 };"
        self.assertRegex(self._status(state), r"^next in [23]\ds$")

    def test_countdown_over_a_minute_keeps_the_seconds(self):
        """Above a minute the seconds stay on screen so the line keeps moving.

        Naming whole minutes alone left the footer unchanged for a minute at a
        time, which reads as a stalled app rather than a waiting one.
        """
        state = "statusState = { lastSuccessTime: NOW - 5, nextPollTime: NOW + 150 };"
        self.assertRegex(self._status(state), r"^next in 2m \d{1,2}s$")

    def test_countdown_past_an_hour_drops_the_seconds(self):
        """Beyond an hour the seconds carry nothing, so hours and minutes suffice."""
        state = "statusState = { lastSuccessTime: NOW - 5, nextPollTime: NOW + 7200 };"
        self.assertRegex(self._status(state), r"^next in 2h \dm$")

    def test_refreshing_replaces_the_countdown(self):
        state = "statusState = { lastSuccessTime: NOW - 10, nextPollTime: NOW + 30, refreshing: true };"
        self.assertEqual(self._status(state), "refreshing")

    def test_error_replaces_the_countdown(self):
        state = "statusState = { lastSuccessTime: NOW - 10, nextPollTime: NOW + 30, error: 'no network' };"
        self.assertEqual(self._status(state), "no network")

    def test_elapsed_fallback_without_a_scheduled_poll(self):
        """With nothing to count down to, the elapsed time takes the line."""
        state = "statusState = { lastSuccessTime: NOW - 10 };"
        self.assertEqual(self._status(state), "updated 10s ago")

    def test_elapsed_fallback_when_the_countdown_has_run_out(self):
        """A poll target already in the past falls back instead of showing 0s."""
        state = "statusState = { lastSuccessTime: NOW - 90, nextPollTime: NOW - 30 };"
        self.assertEqual(self._status(state), "updated 1m ago")


@unittest.skipUnless(_NODE, 'Node.js not available')
class TestUsageBarUpdates(unittest.TestCase):
    """Tests for updateUsageBars/updateBarElement in popup.js."""

    def test_extra_quotas_and_installations_start_collapsed_and_expand(self):
        result = _run_scenario(r'''
translations = {show_more_limits: 'Show {count} more limits', show_fewer_limits: 'Show fewer limits'};
els.moreQuotasBtn = document.createElement('button');
els.moreQuotasText = document.createElement('span');
els.installToggle = document.createElement('button');
els.installRows = document.createElement('dl');
els.installRows.hidden = true;
setupDisclosureButtons();
updateUsageBars([
    makeEntry({key: 'five_hour'}), makeEntry({key: 'seven_day'}),
    makeEntry({key: 'seven_day_sonnet'}), makeEntry({key: 'seven_day_opus'}),
]);
const initial = {
    hidden: els.usageBars.children.slice(2).every(bar => bar.classList.contains('secondary-hidden')),
    label: els.moreQuotasText.textContent,
    expanded: els.moreQuotasBtn.getAttribute('aria-expanded'),
    installsHidden: els.installRows.hidden,
};
els.moreQuotasBtn.dispatchEvent('click');
els.installToggle.dispatchEvent('click');
const opened = {
    hidden: els.usageBars.children.slice(2).some(bar => bar.classList.contains('secondary-hidden')),
    label: els.moreQuotasText.textContent,
    expanded: els.moreQuotasBtn.getAttribute('aria-expanded'),
    installsHidden: els.installRows.hidden,
};
console.log(JSON.stringify({initial, opened}));
''')
        self.assertEqual(result, {
            'initial': {'hidden': True, 'label': 'Show 2 more limits', 'expanded': 'false', 'installsHidden': True},
            'opened': {'hidden': False, 'label': 'Show fewer limits', 'expanded': 'true', 'installsHidden': False},
        })

    def test_percentage_and_bar_colors_follow_time_budget_together(self):
        result = _run_scenario(r'''
updateUsageBars([makeEntry({key: 'codex_primary', pct_text: '51%', fill_pct: 0.51, warn: true, pace_text: 'Elapsed 50% - ahead'})]);
const div = els.usageBars.children[0];
function state() {
    return ['.bar-pct', '.bar-fill', '.pace-text'].map(selector => div.querySelector(selector).classList.contains('warn'));
}
const before = state();
updateUsageBars([makeEntry({key: 'codex_primary', pct_text: '51%', fill_pct: 0.51, warn: false, pace_text: 'Elapsed 51% - within'})]);
const after = state();
const text = div.querySelector('.pace-text').textContent;
updateUsageBars([makeEntry({key: 'codex_primary', pace_text: ''})]);
console.log(JSON.stringify({before, after, text, removed: div.querySelector('.pace-text') === null}));
''')
        self.assertEqual(result, {'before': [True, True, True], 'after': [False, False, False],
                                  'text': 'Elapsed 51% - within', 'removed': True})

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

    def test_reset_text_and_marker_disappear_when_a_codex_window_becomes_unused(self):
        result = _run_scenario('''
const active = makeEntry({key: 'codex_primary', reset_text: 'Resets in 4h 59m', pace_text: 'Elapsed 1%', marker_rel: 0.01});
updateUsageBars([active]);
const bar = els.usageBars.children[0];
updateUsageBars([makeEntry({key: 'codex_primary'})]);
const unused = {reset: bar.querySelector('.reset-text'), pace: bar.querySelector('.pace-text'), marker: bar.querySelector('.bar-marker')};
updateUsageBars([active]);
console.log(JSON.stringify({unused, reset: bar.querySelector('.reset-text').textContent, sameBar: bar === els.usageBars.children[0]}));
''')
        self.assertEqual(result, {'unused': {'reset': None, 'pace': None, 'marker': None}, 'reset': 'Resets in 4h 59m', 'sameBar': True})


@unittest.skipUnless(_NODE, 'Node.js not available')
class TestCodexView(unittest.TestCase):
    _CODEX_PRELUDE = '''
const nodes = {};
document.getElementById = (id) => nodes[id] || (nodes[id] = document.createElement('div'));
for (const key of ['accountSection', 'usageSection', 'extraSection', 'installSection']) els[key] = document.createElement('section');
refreshButton = document.createElement('button');
let renders = 0, interval = null, resolveRead;
renderCodex = () => { renders++; };
setTimeout = (_, ms) => { interval = ms; return 1; };
clearTimeout = () => {};
globalThis.pywebview = {api: {codex_usage: () => new Promise(resolve => { resolveRead = resolve; })}};
'''

    def test_first_switch_holds_the_outgoing_view_until_the_read_lands(self):
        '''The window must resize once, at the swap - not empty out and grow back.'''
        result = _run_scenario(self._CODEX_PRELUDE + '''
selectProvider('codex');
const held = {renders, pending: document.body.classList.contains('pending'),
    spinning: refreshButton.classList.contains('spinning'), interval};
resolveRead({available: true});
setImmediate(() => {
    const swapped = {renders, pending: document.body.classList.contains('pending'),
        spinning: refreshButton.classList.contains('spinning'), interval};
    // A later visit already has the data, so nothing is held the second time.
    selectProvider('claude');
    selectProvider('codex');
    console.log(JSON.stringify({held, swapped, revisit: renders,
        revisitPending: document.body.classList.contains('pending')}));
});
''')
        self.assertEqual(result, {
            'held': {'renders': 0, 'pending': True, 'spinning': True, 'interval': None},
            'swapped': {'renders': 1, 'pending': False, 'spinning': False, 'interval': 60000},
            'revisit': 2, 'revisitPending': False,
        })

    def test_switching_back_releases_the_held_view_and_drops_a_late_response(self):
        result = _run_scenario(self._CODEX_PRELUDE + '''
let restores = 0;
reapplyData = () => { restores++; };
selectProvider('codex');
selectProvider('claude');
const released = {restores, pending: document.body.classList.contains('pending'),
    spinning: refreshButton.classList.contains('spinning')};
resolveRead({available: true});
setImmediate(() => console.log(JSON.stringify({released, renders, interval, provider: selectedProvider})));
''')
        self.assertEqual(result, {
            'released': {'restores': 1, 'pending': False, 'spinning': False},
            'renders': 0, 'interval': None, 'provider': 'claude',
        })

    def test_model_names_render_as_text_and_missing_data(self):
        result = _run_scenario(r'''
translations = {codex_source: 'local only', codex_five_hours: '5h', detail_tokens: 'Tokens', detail_models: 'Models', codex_unavailable: 'missing'};
codexData = {available: true, windows: [{seconds: 18000, tokens: 25, models: [{model: '<script>bad</script>', tokens: 25}]}]};
updateUsageBars([makeEntry({key: 'codex_primary', detail_seconds: 18000})]);
const bar = els.usageBars.children[0];
const collapsed = bar.querySelector('.usage-detail') === null;
bar.dispatchEvent('click');
const model = bar.querySelector('.detail-model-name');
const safe = model.textContent;
const childCount = model.children.length;
codexData = {available: false};
updateUsageBars([makeEntry({key: 'codex_primary', detail_seconds: 18000})]);
console.log(JSON.stringify({safe, childCount, collapsed, empty: bar.querySelector('.usage-detail').textContent}));
''')
        self.assertEqual(result, {'safe': '<script>bad</script>', 'childCount': 0, 'collapsed': True, 'empty': 'missing'})

    def test_each_period_expands_independently_and_refreshes_in_place(self):
        result = _run_scenario(r'''
translations = {detail_tokens: 'Tokens', detail_models: 'Models', codex_source: 'local', codex_five_hours: '5h', codex_seven_days: '7d'};
codexData = {available: true, windows: [
    {seconds: 18000, tokens: 25, models: [{model: 'alpha', tokens: 25}]},
    {seconds: 604800, tokens: 100, models: [{model: 'beta', tokens: 100}]},
]};
const entries = [makeEntry({key: 'codex_primary', detail_seconds: 18000}), makeEntry({key: 'codex_secondary', detail_seconds: 604800})];
updateUsageBars(entries);
const [session, weekly] = els.usageBars.children;
session.dispatchEvent('click');
const independent = !weekly.querySelector('.usage-detail');
weekly.dispatchEvent('keydown', {key: 'Enter', preventDefault() {}});
const weeklyText = weekly.querySelector('.usage-detail').textContent;
codexData.windows[0].tokens = 30;
updateUsageBars(entries);
const sessionText = session.querySelector('.usage-detail').textContent;
session.dispatchEvent('click');
console.log(JSON.stringify({independent, weekly: weeklyText.includes('100') && weeklyText.includes('beta'),
    refreshed: sessionText.includes('30'), collapsed: !session.querySelector('.usage-detail'), weeklyOpen: !!weekly.querySelector('.usage-detail')}));
''')
        self.assertEqual(result, {'independent': True, 'weekly': True, 'refreshed': True, 'collapsed': True, 'weeklyOpen': True})

    def test_installation_footer_switches_provider(self):
        result = _run_scenario(r'''
const nodes = {};
document.getElementById = id => nodes[id] || (nodes[id] = document.createElement('div'));
els.installRows = document.createElement('dl');
els.installSection = document.createElement('section');
translations = {claude_code: 'CLAUDE CODE', changelog: 'Changelog'};
// init() sets the link label once; renderInstallations no longer rewrites it.
document.getElementById('changelogLink').textContent = translations.changelog;
renderInstallations([{name: 'Codex CLI', version: '0.153.0'}], 'codex');
const codex = [nodes.headingClaudeCode.textContent, nodes.changelogLink.textContent, els.installRows.textContent];
renderInstallations([{name: 'CLI', version: '2.0.0'}], 'claude');
const claude = [nodes.headingClaudeCode.textContent, nodes.changelogLink.textContent, els.installRows.textContent];
renderInstallations([], 'codex');
const emptyCodex = els.installSection.classList.contains('visible');
renderInstallations([], 'claude');
console.log(JSON.stringify({codex, claude, emptyCodex, emptyClaude: els.installSection.classList.contains('visible')}));
''')
        self.assertEqual(result, {'codex': ['CODEX', 'Changelog', 'Codex CLI0.153.0'], 'claude': ['CLAUDE CODE', 'Changelog', 'CLI2.0.0'],
                                  'emptyCodex': True, 'emptyClaude': False})

    def test_account_bars_and_email_privacy_on_switch(self):
        result = _run_scenario(r'''
for (const key of ['accountSection', 'usageSection', 'headingUsage', 'planValue', 'planRow']) els[key] = document.createElement('div');
let renderedProfile, bars;
renderAccountRow = profile => { renderedProfile = profile; };
updateUsageBars = usage => { bars = usage; };
renderCodexAccount({profile: {email: 'codex@example.test', name: '', plan: 'Plus'}, usage: [makeEntry({key: 'codex_primary'})]});
const visible = els.accountSection.classList.contains('visible') && els.usageSection.classList.contains('visible');
const plan = els.planValue.textContent;
const key = bars[0].key;
renderCodexAccount(null);
console.log(JSON.stringify({visible, plan, key, cleared: !els.accountSection.classList.contains('visible') && bars.length === 0}));
''')
        self.assertEqual(result, {'visible': True, 'plan': 'Plus', 'key': 'codex_primary', 'cleared': True})

    def test_refresh_schedules_one_minute_after_completion(self):
        result = _run_scenario(r'''
selectedProvider = 'codex';
let interval, calls = 0;
renderCodex = () => {};
setTimeout = (_, ms) => { interval = ms; return 1; };
clearTimeout = () => {};
globalThis.pywebview = {api: {codex_usage: async () => { calls++; return {}; }}};
Promise.all([refreshCodex(), refreshCodex()]).then(() => console.log(JSON.stringify({interval, calls})));
''')
        self.assertEqual(result, {'interval': 60000, 'calls': 1})


if __name__ == '__main__':
    unittest.main()

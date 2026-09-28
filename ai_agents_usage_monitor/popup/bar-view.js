// The bar view: a clock and one card per agent in a single row, drawn from
// the same data as the detail view. Which rows a card shows is decided by
// window length, never by field name. popup.js switches views and loads last.

// Agents whose bar card reads as remaining rather than used. Each card flips
// on its own, so one agent's headroom can sit beside the other's usage. Per
// session: it is a way of looking at the same number, not a setting.
let barRemainingProviders = new Set();
let clockTimerId = null;
let clockDateFormat = null;
let clockTimeFormat = null;
// The clock's separator shows for the first half of every second and hides
// for the second half - one blink per real second - so the clock ticks on
// each half second of the wall clock. The slack lands a tick just past the
// boundary, where a timer firing a moment early would otherwise render the
// half it was meant to leave.
const CLOCK_TICK_MS = 500;
const CLOCK_TICK_SLACK_MS = 15;

/**
 * Prepare the bar view's clock formatters and start it if the bar is up.
 *
 * Both formatters are built once: they are the expensive part of rendering a
 * clock every second, and neither the language nor the 12/24-hour choice can
 * change without the window being reopened.
 *
 * @param {string} langTag - Locale the app's translations were loaded for.
 * @param {string} timeFormat - '24h' or '12h', from the same setting the
 *   reset times are rendered with.
 */
function setupClock(langTag, timeFormat) {
    const locale = langTag || 'en';
    clockDateFormat = new Intl.DateTimeFormat(locale, {month: 'short', day: 'numeric', weekday: 'short'});
    clockTimeFormat = new Intl.DateTimeFormat(locale, {hour: '2-digit', minute: '2-digit', hour12: timeFormat === '12h'});
}

function renderClock() {
    const now = new Date();
    els.clockDate.textContent = clockDateFormat.format(now);
    els.clockTime.setAttribute('aria-label', clockTimeFormat.format(now));
    els.clockTime.replaceChildren(...clockTimeFormat.formatToParts(now).map((part) => {
        const span = document.createElement('span');
        span.textContent = part.value;
        if (part.type === 'literal' && part.value.includes(':')) {
            span.className = 'clock-separator';
            span.classList.toggle('off', now.getMilliseconds() >= CLOCK_TICK_MS);
        }
        return span;
    }));
}

/**
 * Run the clock only while the bar view is showing it.
 *
 * Each tick is scheduled against the wall clock rather than repeated on a
 * fixed interval: an interval keeps the phase of the moment the bar opened
 * and drifts from there, so the blink would neither match the seconds nor
 * keep an even rhythm.
 */
function startClock() {
    if (clockTimerId) return;
    const tick = () => {
        renderClock();
        clockTimerId = setTimeout(tick, CLOCK_TICK_MS - (Date.now() % CLOCK_TICK_MS) + CLOCK_TICK_SLACK_MS);
    };
    tick();
}

function stopClock() {
    if (!clockTimerId) return;
    clearTimeout(clockTimerId);
    clockTimerId = null;
}

/**
 * Render the bar view: the clock, then one card per agent.
 *
 * Which bar counts as the session and which as the weekly quota is decided by
 * duration, not by field name - the shortest window an agent reports is its
 * session, and the shortest of the rest is the quota above it. That keeps a
 * list of quota names out of the page, so a new quota type appears here
 * without the page being taught anything about it.
 */
function renderBarView() {
    renderClock();

    const account = codexData?.account;
    const providers = [
        {key: 'claude', name: 'CLAUDE', usage: lastData?.usage, status: lastData?.status},
        {key: 'codex', name: 'CODEX', usage: account?.usage, status: account?.status, error: codexReadError},
    ];
    if (!els.barCards.children.length) {
        els.barCards.replaceChildren(...providers.map(buildBarCard));
    }

    providers.forEach((provider, index) => {
        const card = els.barCards.children[index];
        const entries = barWindows(provider.usage);
        const showsRemaining = barRemainingProviders.has(provider.key);
        card.querySelector('.bar-card-mode').textContent = showsRemaining ? translations.bar_mode_left : translations.bar_mode_used;
        const rows = card.querySelectorAll('.bar-row');
        rows.forEach((row, rowIndex) => updateBarRow(row, entries[rowIndex], showsRemaining));
        const status = provider.status;
        const error = provider.error || status?.error || (status?.is_error ? status.text : null);
        card.classList.toggle('stale', !!error);
        card.title = [error || (!entries.some(Boolean) ? status?.text || translations.status_refreshing : ''),
            translations.bar_toggle_hint, translations.bar_fill_hint].filter(Boolean).join('\n');
        if (error) rows.forEach((row) => { row.title = [row.title, error].filter(Boolean).join('\n'); });
        card.setAttribute('aria-pressed', showsRemaining);
        card.setAttribute('aria-label', [provider.name, ...Array.from(rows, row => row.title), card.title].filter(Boolean).join(', '));
    });
}

/** Return [session, weekly] for one agent, either of which may be null. */
function barWindows(entries) {
    const timed = (entries || []).filter((entry) => entry.period_seconds);
    if (!timed.length) return [null, null];

    const sorted = [...timed].sort((a, b) => a.period_seconds - b.period_seconds);
    const session = sorted[0];
    const weekly = sorted.find((entry) => entry.period_seconds > session.period_seconds) || null;

    return [session, weekly];
}

function buildBarCard(provider) {
    const card = document.createElement('div');
    card.className = 'bar-card';
    // The stylesheet colors the name by this, in the agent's signature color.
    card.dataset.provider = provider.key;
    card.setAttribute('role', 'button');
    card.setAttribute('tabindex', '0');

    const label = document.createElement('div');
    label.className = 'bar-card-name';
    label.textContent = provider.name;

    const heading = document.createElement('div');
    heading.className = 'bar-card-heading';
    const alert = document.createElement('span');
    alert.className = 'bar-card-alert';
    alert.textContent = '!';
    alert.setAttribute('aria-hidden', 'true');
    const mode = document.createElement('span');
    mode.className = 'bar-card-mode';
    heading.append(label, alert, mode);
    card.append(heading, buildBarRow(false), buildBarRow(true));

    card.addEventListener('click', () => toggleBarRemaining(provider.key));
    card.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            toggleBarRemaining(provider.key);
        }
    });

    return card;
}

function buildBarRow(weekly) {
    const row = document.createElement('div');
    row.className = 'bar-row';
    row.classList.toggle('weekly', weekly);

    const pct = document.createElement('span');
    pct.className = 'bar-row-pct';
    const period = document.createElement('span');
    period.className = 'bar-row-period';
    row.append(period, pct, createBarContainer(null));

    return row;
}

function updateBarRow(row, entry, showsRemaining) {
    row.classList.toggle('empty', !entry);
    row.querySelector('.bar-row-period').textContent = barPeriodLabel(entry?.period_seconds);
    const pct = row.querySelector('.bar-row-pct');
    pct.textContent = entry ? (showsRemaining ? entry.left_text : entry.pct_text) : '\u2014';
    pct.classList.toggle('warn', !!entry?.warn);
    updateBarContainer(row.querySelector('.bar-container'), entry);

    row.title = '';
    if (entry) {
        const template = showsRemaining ? translations.bar_left : translations.bar_used;
        row.title = template.replace('{label}', entry.label).replace('{pct}', pct.textContent);
        row.title = [row.title, entry.reset_text, showsRemaining ? translations.bar_fill_hint : ''].filter(Boolean).join('\n');
    }

}

/** Compact, exact durations; provider field names never determine the label. */
function barPeriodLabel(seconds) {
    if (!Number.isFinite(seconds) || seconds <= 0) return '';
    for (const [unit, suffix] of [[86400, 'd'], [3600, 'h'], [60, 'm'], [1, 's']]) {
        if (seconds % unit === 0) return `${seconds / unit}${suffix}`;
    }
    return `${seconds}s`;
}

/**
 * Flip one agent's percentages in the bar between used and remaining.
 *
 * Only that card's numbers flip; the other agent keeps whichever reading it
 * had. The fill still measures what has been used, because it is read
 * against the elapsed-time marker beside it - inverting the fill would leave
 * that marker comparing against nothing.
 *
 * @param {string} provider - 'claude' or 'codex'.
 */
function toggleBarRemaining(provider) {
    if (!barRemainingProviders.delete(provider)) barRemainingProviders.add(provider);
    renderBarView();
}

let els;
let statusState = {};
let translations = {};
let textTimerId = null;
let popupPinned = false;
let compactHide = [];
let lastData = null;
let emailRevealed = false;
let refreshButton = null;
let selectedProvider = 'claude';
let codexTimerId = null;
let codexBusy = false;
let codexData = null;
let codexReadError = null;
// True while the first Codex read runs with the previous view still on screen.
let codexPending = false;
// Bar keys with their detail panel currently open.  Claude only ever adds
// 'five_hour' and 'seven_day' - session_detail() has no local-log equivalent
// for a model-scoped or unlabeled quota, so those bars are never made
// clickable - and Codex adds its own prefixed keys, so the two views cannot
// collide and an expanded panel stays open only in the tab it belongs to.
let expandedDetail = new Set();
let allQuotasVisible = false;
let installationsVisible = false;
// 'detail' is the full window, 'bar' the single row showing both agents at
// once. The detail view's own state - selected provider, expanded panels,
// revealed email - is left untouched while the bar is up, so switching back
// does not rebuild it.
let viewMode = 'detail';
let viewSwitchBusy = false;
// Whether the bar's percentages read as used or as remaining. Per session:
// it is a way of looking at the same number, not a setting.
let barShowsRemaining = false;
let clockTimerId = null;
let clockDateFormat = null;
let clockTimeFormat = null;

/**
 * Switch the popup between the Claude and Codex views.
 *
 * The window has no scrollbar - its height is whatever the content needs,
 * so every change of what is rendered moves the window edge.  The first
 * Codex read starts the Codex app-server and takes about a second, and
 * emptying the sections for that second would shrink the window and then
 * resize it again once the data arrived.  The view already on screen is
 * therefore left in place - dimmed, with the refresh icon spinning - until
 * there is Codex content to put in its place, so the window resizes exactly
 * once, at the swap.  Later switches render from ``codexData`` immediately.
 */
function selectProvider(provider) {
    if (selectedProvider === provider) return;

    emailRevealed = false;
    allQuotasVisible = false;
    installationsVisible = false;
    selectedProvider = provider;
    document.getElementById('title').setAttribute('aria-pressed', provider === 'claude');
    document.getElementById('codexBtn').setAttribute('aria-pressed', provider === 'codex');
    if (codexTimerId) clearTimeout(codexTimerId);
    codexTimerId = null;

    if (provider === 'claude') {
        endCodexPending();
        reapplyData();
        return;
    }

    if (codexData) {
        renderCodex();
    } else {
        codexPending = true;
        document.body.classList.add('pending');
        setRefreshBusy(true);
    }
    refreshCodex();
}

/**
 * Return true while something on screen needs Codex data.
 *
 * The bar shows both agents at once, so it keeps the Codex reads running
 * regardless of which provider the detail view has selected. Everything that
 * starts or cancels a Codex read asks this rather than testing the selected
 * provider, so the two views cannot disagree about whether the timer runs.
 */
function codexNeeded() {
    return viewMode === 'bar' || selectedProvider === 'codex';
}

/** Release the held view, whether the read arrived or the user switched back. */
function endCodexPending() {
    if (!codexPending) return;
    codexPending = false;
    document.body.classList.remove('pending');
    setRefreshBusy(false);
}

async function refreshCodex() {
    if (codexBusy) return;
    if (codexTimerId) clearTimeout(codexTimerId);
    codexTimerId = null;
    codexBusy = true;
    let failed = false;
    try {
        codexData = await pywebview.api.codex_usage();
    } catch (_) {
        failed = true;
    } finally {
        codexBusy = false;
        codexReadError = failed ? translations.codex_unavailable : null;
        endCodexPending();
        if (codexNeeded()) {
            if (viewMode === 'bar') {
                renderBarView();
            } else {
                renderCodex(failed ? translations.codex_unavailable : null);
            }
            // Schedule against the app's own poll beat, so this view refreshes on the
            // same moment the Claude view does no matter when the tab was opened.
            // Capped at a minute so a cadence change made from the tray menu is
            // picked up promptly; a call landing inside the cooldown costs nothing,
            // because the backend answers it from cache.
            const nextPoll = codexData?.account?.status?.next_poll_time;
            const seconds = nextPoll ? nextPoll - Date.now() / 1000 : (codexData?.refresh_seconds || 60);
            codexTimerId = setTimeout(refreshCodex, Math.min(Math.max(seconds, 1), 60) * 1000);
        }
    }
}

function renderCodex(error) {
    renderCodexAccount(codexData?.account);
    renderInstallations(codexData?.installations || [], 'codex');
    // Extra usage is a Claude-only section; it would otherwise survive the swap.
    els.extraSection.classList.remove('visible');
    if (error || !codexData) {
        updateStatus(error ? {text: error, is_error: true} : {text: translations.status_refreshing});
        return;
    }
    const status = codexData.account?.status || {
        last_success_time: codexData.updated_at,
        next_poll_time: codexData.updated_at + (codexData.refresh_seconds || 60),
    };
    updateStatus({...status, error: status.error || (codexData.partial ? translations.codex_partial : null)});
}

function renderCodexAccount(account) {
    const profile = account?.profile;
    els.accountSection.classList.toggle('visible', !!profile && !compactHidden('account'));
    if (profile) {
        renderAccountRow(profile);
        els.planValue.textContent = profile.plan;
        els.planRow.style.display = profile.plan ? '' : 'none';
    }
    const usage = account?.usage || [];
    els.usageSection.classList.toggle('visible', usage.length > 0);
    els.usageSection.classList.remove('stale');
    els.headingUsage.style.display = '';
    updateUsageBars(usage);
}

/**
 * Set CSS custom properties for theme colors and inject translation strings.
 *
 * Called once by Python after the page loads.  Translations are set as
 * textContent on heading elements so the HTML file stays language-neutral.
 *
 * @param {object} config - { colors, t (translations), app_version, data (initial snapshot) }
 */
function init(config) {
    const s = document.documentElement.style;
    for (const [key, value] of Object.entries(config.colors)) {
        s.setProperty(`--${key.replaceAll('_', '-')}`, value);
    }

    translations = config.t;
    compactHide = config.compact_hide || [];
    setFont(config.font);
    setupClock(config.lang_tag, config.time_format);
    document.getElementById('title').addEventListener('click', () => selectProvider('claude'));
    document.getElementById('codexBtn').addEventListener('click', () => selectProvider('codex'));
    document.getElementById('headingAccount').textContent = translations.account;
    document.getElementById('labelPlan').textContent = translations.plan;
    document.getElementById('headingUsage').textContent = translations.usage;
    document.getElementById('headingExtraUsage').textContent = translations.extra_usage;
    document.getElementById('headingClaudeCode').textContent = translations.claude_code;

    const changelogLink = document.getElementById('changelogLink');
    changelogLink.textContent = translations.changelog;
    changelogLink.addEventListener('click', () => pywebview.api.open_url(selectedProvider));
    setupCloseButtons();
    setupRefreshButton();
    setupAccountRow();
    setupPinButton();
    setupViewButtons();
    setupPopupDrag();

    // The header is a provider switch now, so the app name lives on the footer
    // version instead. The status line beside it already ellipsizes at this
    // width, so the name is a tooltip rather than another column of text.
    const appVersion = document.getElementById('appVersion');
    appVersion.textContent = config.app_version;
    appVersion.title = `${translations.title} v${config.app_version}`;
    const projectBtn = document.getElementById('projectBtn');
    projectBtn.title = translations.project_on_github;
    projectBtn.setAttribute('aria-label', translations.project_on_github);
    projectBtn.addEventListener('click', () => pywebview.api.open_project());

    els = {
        accountSection: document.getElementById('accountSection'),
        emailRow: document.getElementById('emailRow'),
        emailValue: document.getElementById('emailValue'),
        planRow: document.getElementById('planRow'),
        planValue: document.getElementById('planValue'),
        usageSection: document.getElementById('usageSection'),
        headingUsage: document.getElementById('headingUsage'),
        usageBars: document.getElementById('usageBars'),
        moreQuotasBtn: document.getElementById('moreQuotasBtn'),
        moreQuotasText: document.getElementById('moreQuotasText'),
        extraSection: document.getElementById('extraSection'),
        extraSpent: document.getElementById('extraSpent'),
        extraPct: document.getElementById('extraPct'),
        extraBarContainer: document.getElementById('extraBarContainer'),
        extraFill: document.getElementById('extraFill'),
        installSection: document.getElementById('installSection'),
        installToggle: document.getElementById('installToggle'),
        installRows: document.getElementById('installRows'),
        statusSection: document.getElementById('statusSection'),
        statusText: document.getElementById('statusText'),
        barCards: document.getElementById('barCards'),
        clockDate: document.getElementById('clockDate'),
        clockTime: document.getElementById('clockTime'),
    };

    setupDisclosureButtons();
    updateData(config.data);

    // The stored view is applied without telling Python: it is the side that
    // chose the opening view, so the window is already the right width, and a
    // bridge call here would run before the API is guaranteed to be attached.
    if (config.view === 'bar') {
        applyViewMode('bar');
    }

    document.fonts.ready.then(() => requestAnimationFrame(() => document.body.classList.add('open')));
}

function setupDisclosureButtons() {
    els.moreQuotasBtn.addEventListener('click', () => {
        allQuotasVisible = !allQuotasVisible;
        updateQuotaDisclosure(els.usageBars.children.length);
    });
    els.installToggle.addEventListener('click', () => {
        installationsVisible = !installationsVisible;
        els.installRows.hidden = !installationsVisible;
        els.installToggle.setAttribute('aria-expanded', String(installationsVisible));
    });
}

/**
 * Point the detail layout at one of the two typefaces in the stylesheet.
 *
 * Called by Python: once from init(), and again whenever the font is changed
 * from the tray menu while this window is open. The name is also written to
 * the body. The smaller bar view always uses the system stack.
 *
 * @param {string} font - 'system' or 'pretendard'; the bar always uses system fonts.
 */
function setFont(font) {
    const name = font === 'system' ? 'system' : 'pretendard';
    document.documentElement.style.setProperty('--font-stack', `var(--font-${name})`);
    document.body.dataset.font = name;
}

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
            span.classList.toggle('off', now.getSeconds() % 2 === 1);
        }
        return span;
    }));
}

/**
 * Run the clock only while the bar view is showing it.
 *
 * The one-second tick blinks the separator and keeps minute changes prompt.
 */
function startClock() {
    if (clockTimerId) return;
    renderClock();
    clockTimerId = setInterval(renderClock, 1000);
}

function stopClock() {
    if (!clockTimerId) return;
    clearInterval(clockTimerId);
    clockTimerId = null;
}

/**
 * Wire the manual refresh button in the header.
 *
 * The automatic poll keeps running as before; this only lets the user
 * request an immediate fetch.  The button is disabled and its icon spins
 * for the duration of the call, so a second click cannot queue a second
 * fetch, and the Python side additionally rate-limits repeated calls.
 */
function setupRefreshButton() {
    refreshButton = document.getElementById('refreshBtn');
    if (!refreshButton) return;

    refreshButton.setAttribute('aria-label', translations.refresh);
    refreshButton.title = translations.refresh;

    refreshButton.addEventListener('click', () => {
        if (refreshButton.disabled) return;
        setRefreshBusy(true);
        // Minimum spin time so a cache hit does not flash the icon.
        const settled = new Promise((resolve) => setTimeout(resolve, 500));
        Promise.all([
            Promise.resolve(selectedProvider === 'codex' ? refreshCodex() : pywebview.api.refresh()).catch(() => null),
            settled,
        ]).then(() => setRefreshBusy(false));
    });

    setRefreshBusy(false);
}

// A provider switch spins the icon for the first Codex read as well, so the
// busy state is set from outside the button's own setup.
function setRefreshBusy(busy) {
    if (!refreshButton) return;
    refreshButton.disabled = busy;
    refreshButton.classList.toggle('spinning', busy);
}


/**
 * Make the account row toggle between the name and the email address.
 *
 * The email is the one value here worth keeping off the screen by default -
 * the popup is often open during a screen share.  Clicking the row (or
 * pressing Enter/Space on it, since it is focusable) swaps in the address and
 * clicking again puts the name back.
 */
function setupAccountRow() {
    const value = document.getElementById('emailValue');

    function toggle() {
        if (!value.classList.contains('toggleable')) return;
        emailRevealed = !emailRevealed;
        reapplyData();
    }

    value.addEventListener('click', toggle);
    value.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            toggle();
        }
    });
}

/**
 * Render the account row for the current reveal state.
 *
 * With a name available the row shows the name and swaps to the email when
 * revealed, relabelling itself so the value always matches its label.
 * Without one there is nothing to show instead, so the email itself is
 * rendered blurred and the click clears the blur.
 *
 * @param {object} profile - { email, name, plan }
 */
function renderAccountRow(profile) {
    const label = document.getElementById('labelEmail');
    const value = els.emailValue;
    const hasName = !!profile.name;

    els.emailRow.style.display = (profile.email || profile.name) ? '' : 'none';

    if (hasName) {
        label.textContent = emailRevealed ? translations.email : translations.name;
        value.textContent = emailRevealed ? profile.email : profile.name;
    } else {
        label.textContent = translations.email;
        value.textContent = profile.email;
    }

    // Nothing to toggle when the email is missing: the name is not a secret.
    const toggleable = !!profile.email;
    value.classList.toggle('toggleable', toggleable);
    value.classList.toggle('masked', toggleable && !hasName && !emailRevealed);
    value.title = toggleable
        ? (emailRevealed ? translations.hide_email : translations.reveal_email)
        : '';
}


function setupCloseButtons() {
    for (const id of ['closeBtn', 'barCloseBtn']) {
        const button = document.getElementById(id);
        button.title = translations.close_popup;
        button.setAttribute('aria-label', translations.close_popup);
        button.addEventListener('click', () => pywebview.api.close());
    }
}

function setupPinButton() {
    const pinBtn = document.getElementById('pinBtn');

    function render() {
        document.body.classList.toggle('pinned', popupPinned);
        pinBtn.classList.toggle('pinned', popupPinned);
        pinBtn.setAttribute('aria-pressed', popupPinned ? 'true' : 'false');
        pinBtn.setAttribute('aria-label', popupPinned ? translations.unpin_popup : translations.pin_popup);
        pinBtn.title = popupPinned ? translations.unpin_popup : translations.pin_popup;
    }

    pinBtn.addEventListener('click', () => {
        const nextPinned = !popupPinned;
        popupPinned = nextPinned;
        render();
        reapplyData();
        pywebview.api.set_pinned(nextPinned).then((applied) => {
            popupPinned = !!applied;
            render();
            reapplyData();
        }).catch(() => {
            popupPinned = !nextPinned;
            render();
            reapplyData();
        });
    });

    render();
}

/**
 * Return true if a section or usage bar is hidden by the pinned compact view.
 *
 * Hiding only applies while the popup is pinned; unpinned it always shows
 * everything.  `key` is a section key (account, extra_usage, claude_code,
 * status) or a usage field name (e.g. seven_day_opus).
 */
function compactHidden(key) {
    return popupPinned && compactHide.includes(key);
}

// Re-render the last snapshot so compact hiding takes effect on pin toggle.
function reapplyData() {
    // The outgoing view is held on screen on purpose while the first Codex
    // read runs, and rendering an empty Codex view here would undo that.
    if (codexPending) return;

    if (viewMode === 'bar') {
        renderBarView();
        return;
    }

    if (selectedProvider === 'codex') {
        renderCodex();
        return;
    }
    if (lastData) {
        updateData(lastData);
    }
}

/**
 * Wire both directions of the view switch.
 *
 * Each button goes one way only - the header's into the bar, the bar's own
 * back out - so neither has to change what it shows when the view changes.
 */
function setupViewButtons() {
    const toBar = document.getElementById('viewBtn');
    toBar.setAttribute('aria-label', translations.view_bar);
    toBar.title = translations.view_bar;
    toBar.addEventListener('click', () => switchViewMode('bar'));

    const toDetail = document.getElementById('barExpandBtn');
    toDetail.setAttribute('aria-label', translations.view_detail);
    toDetail.title = translations.view_detail;
    toDetail.addEventListener('click', () => switchViewMode('detail'));
}

/**
 * Change the view, telling Python first so the window resizes exactly once.
 *
 * The width belongs to the mode and has to be in place before the new
 * content's height is measured; doing it the other way round resizes the
 * window twice - into the new height at the old width, then again when the
 * width catches up.
 */
async function switchViewMode(mode) {
    if (viewMode === mode || viewSwitchBusy) return;

    viewSwitchBusy = true;
    try {
        await pywebview.api.set_view_mode(mode);
        applyViewMode(mode);
    } catch (_) {
        // Keep the layout paired with the host's width if the bridge fails.
    } finally {
        viewSwitchBusy = false;
    }
}

function applyViewMode(mode) {
    if (viewMode === mode) return;

    viewMode = mode;
    document.body.classList.toggle('bar-mode', mode === 'bar');

    if (mode === 'bar') {
        startClock();
        // A first Codex read takes about a second. The empty row holds the
        // card's height for it, so there is nothing to gain by waiting.
        renderBarView();
        refreshCodex();
        return;
    }

    stopClock();
    if (codexTimerId && !codexNeeded()) {
        clearTimeout(codexTimerId);
        codexTimerId = null;
    }
    reapplyData();
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

    const providers = [
        {name: 'CLAUDE', usage: lastData?.usage, status: lastData?.status},
        {name: 'CODEX', usage: codexData?.account?.usage, status: codexData?.account?.status, error: codexReadError},
    ];
    if (!els.barCards.children.length) {
        els.barCards.replaceChildren(...providers.map((provider) => buildBarCard(provider.name)));
    }

    providers.forEach((provider, index) => {
        const card = els.barCards.children[index];
        const entries = barWindows(provider.usage);
        const rows = card.querySelectorAll('.bar-row');
        rows.forEach((row, rowIndex) => updateBarRow(row, entries[rowIndex]));
        const status = provider.status;
        const error = provider.error || status?.error || (status?.is_error ? status.text : null);
        card.classList.toggle('stale', !!error);
        card.title = error || (!entries.some(Boolean) ? status?.text || translations.status_refreshing : '');
        card.setAttribute('aria-pressed', barShowsRemaining);
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

function buildBarCard(name) {
    const card = document.createElement('div');
    card.className = 'bar-card';
    card.setAttribute('role', 'button');
    card.setAttribute('tabindex', '0');

    const label = document.createElement('div');
    label.className = 'bar-card-name';
    label.textContent = name;

    card.append(label, buildBarRow(false), buildBarRow(true));

    card.addEventListener('click', toggleBarRemaining);
    card.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            toggleBarRemaining();
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
    row.append(pct, createBarContainer(null));

    return row;
}

function updateBarRow(row, entry) {
    row.classList.toggle('empty', !entry);
    const pct = row.querySelector('.bar-row-pct');
    pct.textContent = entry ? (barShowsRemaining ? entry.left_text : entry.pct_text) : '\u2014';
    pct.classList.toggle('warn', !!entry?.warn);
    updateBarContainer(row.querySelector('.bar-container'), entry);

    row.title = '';
    if (entry) {
        const template = barShowsRemaining ? translations.bar_left : translations.bar_used;
        row.title = template.replace('{label}', entry.label).replace('{pct}', pct.textContent);
    }

}

/**
 * Flip every percentage in the bar between used and remaining.
 *
 * Only the numbers flip. The fill still measures what has been used, because
 * it is read against the elapsed-time marker beside it - inverting the fill
 * would leave that marker comparing against nothing.
 */
function toggleBarRemaining() {
    barShowsRemaining = !barShowsRemaining;
    renderBarView();
}

/**
 * Build the track, fill, dividers and elapsed-time marker for one entry.
 *
 * Shared by the detail bars and the bar view's rows so both mark elapsed time
 * the same way; an entry of null renders an empty track.
 */
function createBarContainer(entry) {
    const container = document.createElement('div');
    container.className = 'bar-container';
    const fill = document.createElement('div');
    fill.className = 'bar-fill';
    container.appendChild(fill);
    updateBarContainer(container, entry);
    fill.style.width = '0%';

    return container;
}

function updateBarContainer(container, entry) {
    const fill = container.querySelector('.bar-fill');
    fill.style.width = `${(entry?.fill_pct || 0) * 100}%`;
    fill.classList.toggle('warn', !!entry?.warn);

    for (const divider of container.querySelectorAll('.bar-divider')) divider.remove();
    for (const pos of entry?.dividers || []) {
        const divider = document.createElement('div');
        divider.className = 'bar-divider';
        divider.style.left = `calc(${pos * 100}% - 1px)`;
        container.appendChild(divider);
    }

    let marker = container.querySelector('.bar-marker');
    if (entry?.marker_rel != null) {
        if (!marker) {
            marker = document.createElement('div');
            marker.className = 'bar-marker';
            container.appendChild(marker);
        }
        marker.style.left = `calc(${entry.marker_rel * 100}% - 1px)`;
    } else if (marker) {
        marker.remove();
    }
}

/**
 * Wire the drag handles for the bar and the pinned detail popup.
 *
 * The bar view hides the header, so the clock takes over as its handle - it
 * is the one part of that row that is neither a card nor a button.
 */
function setupPopupDrag() {
    const handles = [document.querySelector('header'), document.getElementById('clockWidget')];
    let dragging = false;
    let pointerId = null;
    let activeHandle = null;
    let bridgePending = false;

    function setDragging(active) {
        dragging = active;
        for (const handle of handles) {
            handle.classList.toggle('dragging', active);
        }
    }

    function finishDrag() {
        const wasDragging = dragging;
        const releasedId = pointerId;
        pointerId = null;
        setDragging(false);
        if (activeHandle?.hasPointerCapture(releasedId)) {
            activeHandle.releasePointerCapture(releasedId);
        }
        activeHandle = null;
        if (wasDragging) {
            bridgePending = true;
            pywebview.api.end_drag().catch(() => {}).finally(() => { bridgePending = false; });
        }
    }

    for (const handle of handles) {
        handle.addEventListener('pointerdown', (event) => {
            if ((!popupPinned && viewMode !== 'bar') || event.button !== 0 || event.target.closest('button')) {
                return;
            }
            if (pointerId !== null || bridgePending) {
                return;
            }
            event.preventDefault();
            pointerId = event.pointerId;
            activeHandle = handle;
            // Keep receiving motion even when the cursor leaves this small window.
            handle.setPointerCapture(pointerId);
            bridgePending = true;
            pywebview.api.begin_drag().then((started) => {
                // A quick release can arrive before the Python bridge responds.
                if (pointerId === null) {
                    if (started) return pywebview.api.end_drag();
                } else if (started) {
                    setDragging(true);
                } else {
                    finishDrag();
                }
            }).catch(finishDrag).finally(() => { bridgePending = false; });
        });
        handle.addEventListener('lostpointercapture', (event) => {
            if (event.pointerId === pointerId) finishDrag();
        });
    }

    document.addEventListener('pointermove', (event) => {
        if (event.pointerId !== pointerId) return;
        if (!(event.buttons & 1)) {
            finishDrag();
            return;
        }
        if (dragging) pywebview.api.drag().catch(() => {});
    });

    for (const type of ['pointerup', 'pointercancel']) {
        document.addEventListener(type, (event) => {
            if (event.pointerId === pointerId) finishDrag();
        });
    }
}

/**
 * Update all popup sections with fresh data from Python.
 *
 * @param {object} data - Pre-formatted snapshot from _snapshot_to_dict().
 */
function updateData(data) {
    lastData = data;
    if (viewMode === 'bar') {
        renderBarView();
        return;
    }
    if (selectedProvider === 'codex') return;

    const hasProfile = !!data.profile;
    const accountVisible = hasProfile && !compactHidden('account');
    els.accountSection.classList.toggle('visible', accountVisible);
    if (hasProfile) {
        renderAccountRow(data.profile);
        els.planValue.textContent = data.profile.plan;
        els.planRow.style.display = data.profile.plan ? '' : 'none';
    }

    const usage = (data.usage || []).filter((entry) => !compactHidden(entry.key));
    const hasUsage = !!usage.length;
    els.usageSection.classList.toggle('visible', hasUsage);
    if (hasUsage) {
        updateUsageBars(usage);
    }

    const hasExtra = !!data.extra;
    const extraVisible = hasExtra && !compactHidden('extra_usage');
    els.extraSection.classList.toggle('visible', extraVisible);
    if (hasExtra) {
        els.extraSpent.textContent = data.extra.spent_text;
        els.extraPct.style.display = data.extra.has_limit ? '' : 'none';
        els.extraPct.textContent = data.extra.pct_text;
        els.extraBarContainer.style.display = data.extra.has_limit ? '' : 'none';
        els.extraFill.style.width = `${data.extra.fill_pct * 100}%`;
    }

    const installsVisible = !!data.installations?.length && !compactHidden('claude_code');

    // The "Usage" heading only labels the bars against the other sections;
    // when the usage bars stand alone, drop the now-redundant heading.
    els.headingUsage.style.display = (hasUsage && !accountVisible && !extraVisible && !installsVisible) ? 'none' : '';

    renderInstallations(data.installations || [], 'claude');

    updateStatus(data.status);
}

/**
 * Fill the footer's installed-version list for one provider.
 *
 * The Codex section stays visible even when nothing is installed, so its
 * changelog link - the Codex release notes - is always reachable.
 */
function renderInstallations(installations, provider) {
    document.getElementById('headingClaudeCode').textContent = provider === 'codex' ? 'CODEX' : translations.claude_code;
    els.installSection.classList.toggle('visible', (installations.length > 0 || provider === 'codex') && !compactHidden('claude_code'));
    els.installRows.hidden = !installationsVisible;
    els.installToggle?.setAttribute('aria-expanded', String(installationsVisible));
    els.installRows.replaceChildren(...installations.map(inst => {
        const row = document.createElement('div');
        const name = document.createElement('dt');
        name.textContent = inst.name;
        const version = document.createElement('dd');
        version.textContent = inst.version;
        row.append(name, version);
        return row;
    }));
}

/**
 * Update the status footer with live timer data or static text.
 *
 * Live mode (has last_success_time): starts a 1-second interval for
 * the text counter.  Static mode (has text): shows plain text.
 */
function updateStatus(status) {
    if (textTimerId) {
        clearInterval(textTimerId);
        textTimerId = null;
    }

    if (!status) {
        els.statusSection.classList.remove('visible');
        return;
    }

    // Keep the live timer running even when the footer is hidden in compact
    // view, so the stale-dimming of the usage bars still updates.
    els.statusSection.classList.toggle('visible', !compactHidden('status'));

    if (status.last_success_time !== undefined) {
        statusState = {
            lastSuccessTime: status.last_success_time,
            nextPollTime: status.next_poll_time,
            refreshing: status.refreshing,
            error: status.error,
        };
        els.statusSection.classList.toggle('error', !!status.error);
        tickStatusText();
        textTimerId = setInterval(tickStatusText, 1000);
    } else {
        statusState = {};
        els.statusText.textContent = status.text || '';
        els.statusText.title = status.is_error ? (status.text || '') : '';
        els.statusSection.classList.toggle('error', !!status.is_error);
    }
}

/**
 * Build and display the status text from current state.
 *
 * "Next update in Ym" - the countdown alone.  It already implies how fresh
 * the data is, and one moving number reads better in the narrow footer than
 * two counting in opposite directions.  Refreshing or an error replaces it;
 * "Updated X ago" is the fallback for when no next poll is scheduled and
 * there is nothing to count down to.
 */
function tickStatusText() {
    if (!statusState.lastSuccessTime) return;

    const now = Date.now() / 1000;
    const isStale = !!statusState.nextPollTime && (now > statusState.nextPollTime + 30);
    els.usageSection.classList.toggle('stale', isStale);
    els.extraSection.classList.toggle('stale', isStale);

    const secondsUntil = statusState.nextPollTime ? Math.max(0, Math.floor(statusState.nextPollTime - now)) : 0;

    let text;
    if (statusState.refreshing) {
        text = translations.status_refreshing;
    } else if (statusState.error) {
        text = statusState.error;
    } else if (secondsUntil > 0) {
        text = translations.status_next_update.replace('{duration}', formatCountdown(secondsUntil));
    } else {
        text = formatDuration(Math.max(0, Math.floor(now - statusState.lastSuccessTime)));
    }

    els.statusText.textContent = text;
    // Errors are raw API messages that can overflow; reveal the full text on hover.
    els.statusText.title = statusState.error ? text : '';
}

/**
 * Format seconds into a localized "Updated Xs ago" / "Updated Xm ago" string.
 */
function formatDuration(totalSeconds) {
    if (totalSeconds < 60) {
        return translations.status_updated_s.replace('{s}', totalSeconds);
    }

    const totalMin = Math.floor(totalSeconds / 60);
    const hours = Math.floor(totalMin / 60);
    const mins = totalMin % 60;

    let duration;
    if (hours > 0) {
        duration = translations.duration_hm.replace('{h}', hours).replace('{m}', mins);
    } else {
        duration = translations.duration_m.replace('{m}', totalMin);
    }
    return translations.status_updated.replace('{duration}', duration);
}

/**
 * Format a countdown in seconds into a localized duration string.
 *
 * Below an hour the seconds are always shown, so the footer keeps moving
 * every tick.  Naming whole minutes alone left it standing still for a minute
 * at a time, which reads as a stalled app rather than a waiting one.  Past an
 * hour the seconds stop carrying information and hours plus minutes are
 * enough.
 */
function formatCountdown(totalSeconds) {
    if (totalSeconds < 60) {
        return translations.duration_s.replace('{s}', totalSeconds);
    }

    if (totalSeconds < 3600) {
        const mins = Math.floor(totalSeconds / 60);
        return translations.duration_ms.replace('{m}', mins).replace('{s}', totalSeconds % 60);
    }

    const totalMin = Math.ceil(totalSeconds / 60);
    return translations.duration_hm.replace('{h}', Math.floor(totalMin / 60)).replace('{m}', totalMin % 60);
}

// Bar keys that offer local-log detail on click. Kept in one place so the
// click handler, the render functions, and the tests all agree on which
// two fields this applies to.
const DETAIL_FIELDS = new Set(['five_hour', 'seven_day']);

function updateUsageBars(entries) {
    // Rebuild whenever the field set changes, not only the count - after an
    // account switch the same number of bars can carry different quotas, and
    // an in-place update would show the new values under the old labels.
    const bars = els.usageBars.children;
    const sameFields = entries.length === bars.length
        && entries.every((entry, i) => bars[i].dataset.key === entry.key
            && bars[i].dataset.detailSeconds === String(entry.detail_seconds || ''));

    if (!sameFields) {
        els.usageBars.replaceChildren(...entries.map(createBarElement));
        requestAnimationFrame(() => {
            for (let i = 0; i < entries.length; i++) {
                els.usageBars.children[i].querySelector('.bar-fill').style.width =
                    `${entries[i].fill_pct * 100}%`;
            }
        });
    } else {
        for (let i = 0; i < entries.length; i++) {
            updateBarElement(els.usageBars.children[i], entries[i]);
        }
    }
    updateQuotaDisclosure(entries.length);
}

function updateQuotaDisclosure(count) {
    const extraCount = Math.max(0, count - 2);
    if (!extraCount) allQuotasVisible = false;
    for (let i = 0; i < count; i++) {
        els.usageBars.children[i].classList.toggle('secondary-hidden', i >= 2 && !allQuotasVisible);
    }
    if (!els.moreQuotasBtn) return;
    els.moreQuotasBtn.hidden = extraCount === 0;
    els.moreQuotasBtn.setAttribute('aria-expanded', String(allQuotasVisible));
    els.moreQuotasText.textContent = allQuotasVisible
        ? translations.show_fewer_limits
        : translations.show_more_limits.replace('{count}', extraCount);
}

function createBarElement(entry) {
    const div = document.createElement('div');
    div.className = 'usage-entry';
    div.dataset.key = entry.key;
    div.dataset.detailSeconds = String(entry.detail_seconds || '');

    const header = document.createElement('div');
    header.className = 'bar-header';
    const label = document.createElement('span');
    label.textContent = entry.label;
    const pct = document.createElement('span');
    pct.className = 'bar-pct';
    pct.textContent = entry.pct_text;
    pct.classList.toggle('warn', entry.warn);
    header.append(label, pct);

    const container = createBarContainer(entry);

    div.append(header, container);
    updatePaceText(div, entry);

    if (entry.reset_text) {
        const reset = document.createElement('div');
        reset.className = 'reset-text';
        reset.textContent = entry.reset_text;
        div.appendChild(reset);
    }

    if (DETAIL_FIELDS.has(entry.key) || entry.detail_seconds) {
        div.classList.add('detail-toggleable');
        div.setAttribute('role', 'button');
        div.setAttribute('tabindex', '0');
        div.setAttribute('aria-expanded', 'false');
        div.addEventListener('click', () => toggleDetail(entry.key, div));
        div.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                toggleDetail(entry.key, div);
            }
        });
        // Bars are torn down and rebuilt whenever the field set changes
        // (see updateUsageBars); re-open and re-fetch so an expanded panel
        // survives that rebuild instead of silently vanishing.
        if (expandedDetail.has(entry.key)) {
            openDetail(entry.key, div);
        }
    }

    return div;
}

function updateBarElement(div, entry) {
    if (entry.detail_seconds && expandedDetail.has(entry.key)) renderCodexDetail(div);
    const pct = div.querySelector('.bar-pct');
    pct.textContent = entry.pct_text;
    pct.classList.toggle('warn', entry.warn);
    updatePaceText(div, entry);

    updateBarContainer(div.querySelector('.bar-container'), entry);

    let resetEl = div.querySelector('.reset-text');
    if (entry.reset_text) {
        if (!resetEl) {
            resetEl = document.createElement('div');
            resetEl.className = 'reset-text';
            // Insert ahead of an already-open detail panel rather than
            // appending, so a reset-text that appears after the panel was
            // opened (e.g. a fresh five_hour bar gets its first reset time)
            // does not land below it.
            div.insertBefore(resetEl, div.querySelector('.usage-detail'));
        }
        resetEl.textContent = entry.reset_text;
    } else if (resetEl) {
        resetEl.remove();
    }
}

function updatePaceText(div, entry) {
    let pace = div.querySelector('.pace-text');
    if (!entry.pace_text) {
        if (pace) pace.remove();
        return;
    }
    if (!pace) {
        pace = document.createElement('div');
        pace.className = 'pace-text';
        div.insertBefore(pace, div.querySelector('.reset-text') || div.querySelector('.usage-detail'));
    }
    pace.textContent = entry.pace_text;
    pace.classList.toggle('warn', entry.warn);
}

/**
 * Toggle the local-log detail panel under a five_hour/seven_day bar.
 *
 * @param {string} key - 'five_hour' or 'seven_day'.
 * @param {HTMLElement} div - the bar's .usage-entry element.
 */
function toggleDetail(key, div) {
    if (expandedDetail.has(key)) {
        expandedDetail.delete(key);
        div.classList.remove('expanded');
        div.setAttribute('aria-expanded', 'false');
        div.querySelector('.usage-detail')?.remove();
        return;
    }
    openDetail(key, div);
}

function openDetail(key, div) {
    expandedDetail.add(key);
    div.classList.add('expanded');
    div.setAttribute('aria-expanded', 'true');
    if (div.dataset.detailSeconds) {
        renderCodexDetail(div);
        return;
    }
    renderDetailLoading(div);

    if (!window.pywebview?.api?.session_detail) {
        renderDetailUnavailable(div);
        return;
    }

    pywebview.api.session_detail(key).then((result) => {
        // The panel may have been collapsed while this call was in flight.
        // (A full bar rebuild - see updateUsageBars - re-triggers openDetail
        // on the fresh element instead, so this stale call simply has
        // nothing left to update.)
        if (!expandedDetail.has(key)) return;
        renderDetail(div, result);
    }).catch(() => {
        if (!expandedDetail.has(key)) return;
        renderDetailUnavailable(div);
    });
}

function renderCodexDetail(div) {
    const seconds = Number(div.dataset.detailSeconds);
    const usage = codexData?.windows?.find(window => window.seconds === seconds);
    if (!codexData?.available || !usage) {
        const panel = detailPanel(div);
        panel.classList.add('error');
        panel.textContent = translations.codex_unavailable;
        return;
    }
    const note = `${usage.period_text}. ${translations.codex_source}`;
    renderDetail(div, {
        tokens: usage.tokens.toLocaleString(),
        models: usage.models.map(model => ({
            model: model.model, tokens: model.tokens.toLocaleString(),
            pct: usage.tokens > 0 ? (model.tokens / usage.tokens * 100).toFixed(1) : '0.0',
        })),
        source: codexData.partial ? `${note} ${translations.codex_partial}` : note,
    });
}

/** Get (creating if needed) the .usage-detail panel, placed after reset-text. */
function detailPanel(div) {
    let panel = div.querySelector('.usage-detail');
    if (!panel) {
        panel = document.createElement('div');
        panel.className = 'usage-detail';
        div.appendChild(panel);
    }
    return panel;
}

function renderDetailLoading(div) {
    const panel = detailPanel(div);
    panel.classList.remove('error');
    panel.textContent = translations.detail_loading;
}

function renderDetailUnavailable(div) {
    const panel = detailPanel(div);
    panel.classList.add('error');
    panel.textContent = translations.detail_unavailable;
}

/**
 * Render a session_detail() result into the bar's detail panel.
 *
 * @param {HTMLElement} div - the bar's .usage-entry element.
 * @param {object} result - { unavailable, tokens, messages, estimated_total, models }
 */
function renderDetail(div, result) {
    const panel = detailPanel(div);
    panel.classList.remove('error');
    panel.replaceChildren();

    if (result.unavailable) {
        panel.classList.add('error');
        panel.textContent = translations.detail_unavailable;
        return;
    }

    if (result.tokens === '0' && result.messages === '0') {
        // Not "you used nothing" - the local logs only cover Claude Code, so
        // a period spent on claude.ai or the desktop app reads as empty here.
        // The source note below spells that out.
        const empty = document.createElement('div');
        empty.textContent = translations.detail_no_usage;
        panel.appendChild(empty);
        panel.appendChild(createSourceNote());
        return;
    }

    const counts = document.createElement('div');
    counts.className = 'detail-counts';

    const tokenLine = document.createElement('span');
    tokenLine.textContent = `${translations.detail_tokens} ${result.tokens}`;
    if (result.estimated_total) {
        const est = document.createElement('span');
        est.className = 'detail-estimated';
        est.textContent = ' ' + translations.detail_estimated.replace('{total}', result.estimated_total);
        tokenLine.appendChild(est);
    }

    counts.appendChild(tokenLine);
    if (result.messages !== undefined) {
        const messageLine = document.createElement('span');
        messageLine.textContent = `${translations.detail_messages} ${result.messages}`;
        counts.appendChild(messageLine);
    }
    panel.appendChild(counts);

    if (result.models.length) {
        const heading = document.createElement('div');
        heading.className = 'detail-models-heading';
        heading.textContent = translations.detail_models;
        panel.appendChild(heading);

        const list = document.createElement('div');
        list.className = 'detail-models';
        for (const model of result.models) {
            list.appendChild(createModelRow(model));
        }
        panel.appendChild(list);
    }

    panel.appendChild(createSourceNote(result.source));
}

/** Footnote naming where these numbers come from, and what they exclude. */
function createSourceNote(source) {
    const note = document.createElement('div');
    note.className = 'detail-source';
    note.textContent = source || translations.detail_source;
    return note;
}

function createModelRow(model) {
    const row = document.createElement('div');
    row.className = 'detail-model-row';

    const name = document.createElement('span');
    name.className = 'detail-model-name';
    name.textContent = model.model;

    const track = document.createElement('div');
    track.className = 'detail-model-bar';
    const fill = document.createElement('div');
    fill.className = 'detail-model-bar-fill';
    fill.style.width = `${model.pct}%`;
    track.appendChild(fill);

    const pct = document.createElement('span');
    pct.className = 'detail-model-pct';
    pct.textContent = `${model.pct}%`;

    row.append(name, track, pct);
    return row;
}

// Report content height changes to the host (pywebview or dev.html iframe parent).
new ResizeObserver(() => {
    const height = document.body.scrollHeight;
    if (window.pywebview?.api?.report_height) {
        pywebview.api.report_height(height);
    }
}).observe(document.body);

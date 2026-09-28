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
let allQuotasVisible = false;
let installationsVisible = false;
// 'detail' is the full window, 'bar' the single row showing both agents at
// once. The detail view's own state - selected provider, expanded panels,
// revealed email - is left untouched while the bar is up, so switching back
// does not rebuild it.
let viewMode = 'detail';
let viewSwitchBusy = false;

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
    markSelectedProvider(provider);
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

/** Record which agent the detail view shows and press its header tab. */
function markSelectedProvider(provider) {
    selectedProvider = provider;
    document.getElementById('title').setAttribute('aria-pressed', provider === 'claude');
    document.getElementById('codexBtn').setAttribute('aria-pressed', provider === 'codex');
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
    const barOnly = viewMode === 'bar';
    let failed = false;
    try {
        if (barOnly) {
            codexData = {...codexData, account: await pywebview.api.codex_account()};
        } else {
            codexData = await pywebview.api.codex_usage();
        }
    } catch (_) {
        failed = true;
    } finally {
        codexBusy = false;
        codexReadError = failed ? translations.codex_unavailable : null;
        // A bar read cannot supply local details if the view changed in flight.
        if (barOnly && viewMode === 'detail' && selectedProvider === 'codex') {
            refreshCodex();
            return;
        }
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
    // Codex reports only a balance of purchased credits - no amount spent and no limit.
    const credits = codexData?.account?.credits_text;
    renderExtraSection(credits ? {spent_text: '', has_limit: false, balance_text: credits} : null);
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

/**
 * Fill the extra-usage section for either agent and return whether it shows.
 *
 * Claude brings the amount spent, a percentage, a bar and the prepaid balance;
 * Codex brings only its credit balance.  Every part hides when its text is
 * absent, so switching agents never leaves the other one's numbers behind.
 */
function renderExtraSection(extra) {
    const visible = !!extra && !compactHidden('extra_usage');
    els.extraSection.classList.toggle('visible', visible);
    if (!extra) return visible;

    els.extraHeader.style.display = extra.spent_text ? '' : 'none';
    els.extraSpent.textContent = extra.spent_text || '';
    els.extraPct.style.display = extra.has_limit ? '' : 'none';
    els.extraPct.textContent = extra.pct_text || '';
    els.extraBarContainer.style.display = extra.has_limit ? '' : 'none';
    els.extraFill.style.width = `${(extra.fill_pct || 0) * 100}%`;
    els.extraBalance.textContent = extra.balance_text || '';
    els.extraBalance.hidden = !extra.balance_text;
    return visible;
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
    // Where Windows rounds the window, the page draws no edge stroke: the
    // shadow sets the window apart, and a stroke would be cut at the corners.
    document.documentElement.toggleAttribute('data-framed', Boolean(config.framed));
    setMaterial(config.material);

    translations = config.t;
    codexData = config.codex_data || null;
    compactHide = config.compact_hide || [];
    // The stylesheet sets heading tracking by :lang(), so this has to be the
    // app's language, not the static attribute.
    document.documentElement.lang = config.lang_tag;
    setupClock(config.lang_tag, config.time_format);
    document.getElementById('clockWidget').title = translations.drag_to_move;
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
    setupGlint();

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
        extraHeader: document.getElementById('extraHeader'),
        extraSpent: document.getElementById('extraSpent'),
        extraPct: document.getElementById('extraPct'),
        extraBarContainer: document.getElementById('extraBarContainer'),
        extraFill: document.getElementById('extraFill'),
        extraBalance: document.getElementById('extraBalance'),
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
    // The detail view opens on the agent the tray icon follows. The bar shows
    // both agents, so there the choice only sets the tab a switch back to the
    // detail view lands on, and the bar still reads Codex quotas alone.
    const opensOnCodex = config.provider === 'codex';
    if (config.view === 'bar') {
        if (opensOnCodex) markSelectedProvider('codex');
        applyViewMode('bar');
    } else if (opensOnCodex) {
        // Before the first Codex read has finished, this holds the Claude view
        // dimmed until it lands, exactly as a first switch to the tab does.
        selectProvider('codex');
    } else {
        // Prepare the other tab while Claude is visible. Reads share the app's
        // caches, so reopening cannot bypass the account cooldown or backoff.
        refreshCodex();
    }

    document.fonts.ready.then(() => requestAnimationFrame(() => document.body.classList.add('open')));
}

/**
 * Draw the page as matte or glass.
 *
 * Only the attribute changes: matte.css and glass.css hold every value each
 * material draws with. Python calls this only once the window can carry the
 * material - after the native glass layer is on when entering glass, before
 * it goes when leaving.
 *
 * @param {string} material - 'matte' or 'glass'
 */
function setMaterial(material) {
    document.documentElement.dataset.material = material === 'glass' ? 'glass' : 'matte';
}

/**
 * Keep the glass glint under the pointer.
 *
 * Only the pointer's viewport position is recorded, on the root: glass.css
 * draws each pane's glint against the viewport, so the page needs no list of
 * which elements are panes - that list lives in glass.css alone - and
 * cards rebuilt on a data push pick the glint up without new listeners. The
 * position is written in either material; matte simply never draws it.
 */
function setupGlint() {
    document.addEventListener('pointermove', (event) => {
        const root = document.documentElement.style;
        root.setProperty('--glint-x', `${event.clientX}px`);
        root.setProperty('--glint-y', `${event.clientY}px`);
    });
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
    if (selectedProvider === 'codex') refreshCodex();
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

    const extraVisible = renderExtraSection(data.extra);

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

// Report content height changes to the host (pywebview or dev.html iframe parent).
new ResizeObserver(() => {
    const height = document.body.scrollHeight;
    if (window.pywebview?.api?.report_height) {
        pywebview.api.report_height(height);
    }
}).observe(document.body);

// Usage cards: the detail view's quota bars, the track they share with the
// bar view, and the local detail panel a card expands into. popup.js holds
// the page state these read (els, translations, codexData) and loads last.

// Bar keys with their detail panel currently open.  Claude only ever adds the
// bars Python marks with session_detail - the local logs have no equivalent
// for a model-scoped or unlabeled quota, so those bars are never made
// clickable - and Codex adds its own prefixed keys, so the two views cannot
// collide and an expanded panel stays open only in the tab it belongs to.
let expandedDetail = new Set();

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
    div.dataset.periodSeconds = String(entry.period_seconds || '');

    const header = document.createElement('div');
    header.className = 'bar-header';
    const label = document.createElement('span');
    label.className = 'quota-label';
    const labelText = document.createElement('span');
    labelText.textContent = entry.label;
    label.appendChild(labelText);
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

    // Python decides which bars carry local detail: session_detail for a
    // Claude quota the transcripts can reproduce, detail_seconds for a Codex
    // window the local rollouts cover.
    if (entry.session_detail || entry.detail_seconds) {
        const arrow = document.createElement('span');
        arrow.className = 'disclosure-arrow';
        arrow.setAttribute('aria-hidden', 'true');
        label.appendChild(arrow);
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
 * Toggle the local-log detail panel under a bar that carries one.
 *
 * @param {string} key - the bar's field key.
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
    const note = translations.codex_source;
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
        // The message names Claude Code for that reason, which lets the source
        // note follow the same once-per-list rule as a panel with data.
        const empty = document.createElement('div');
        empty.textContent = translations.detail_no_usage;
        panel.appendChild(empty);
        if (carriesSourceNote(div)) panel.appendChild(createSourceNote(result.source));
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

    if (carriesSourceNote(div)) panel.appendChild(createSourceNote(result.source));
}

/**
 * Return true when this bar's panel should carry the source note.
 *
 * The note reads the same under every panel, so with the session and the
 * weekly panel open it would appear twice.  It goes under the longest
 * window among the expandable bars - the weekly one - and nowhere else,
 * whether or not that bar's period is empty.
 */
function carriesSourceNote(div) {
    const own = Number(div.dataset.periodSeconds) || 0;
    const bars = div.parentNode ? Array.from(div.parentNode.children) : [div];
    return bars.every((bar) => !bar.classList.contains('detail-toggleable') || (Number(bar.dataset.periodSeconds) || 0) <= own);
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

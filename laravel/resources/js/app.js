const API = (import.meta.env?.VITE_NUTRIREC_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const REQUEST_TIMEOUT_MS = 30000;
const KEY = 'nutrirec-session-v1';

export function makePayload(state) {
    const target = Number(state.target?.id);
    const prioritas = Number(state.prioritas?.id);
    const ids = state.status_alergi === true ? (state.alergen || []).map(x => Number(x.id)) : [];
    if (!Number.isInteger(target) || target <= 0 || !Number.isInteger(prioritas) || prioritas <= 0 || typeof state.status_alergi !== 'boolean' || (state.status_alergi && (!ids.length || ids.some(id => !Number.isInteger(id) || id <= 0)))) {
        throw new Error('Lengkapi pilihan kalori, prioritas, dan alergi terlebih dahulu.');
    }
    return { status_alergi: state.status_alergi, alergen_ids: ids, target_kalori_id: target, prioritas_id: prioritas };
}

export async function requestApi(path, options = {}, fetcher = fetch) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
        const response = await fetcher(`${API}${path}`, { ...options, signal: controller.signal });
        let body = null;
        try { body = await response.json(); } catch { /* Server may return non-JSON errors. */ }
        if (!response.ok) {
            const detail = typeof body?.detail === 'string' ? body.detail : '';
            if (response.status === 400) throw new Error(detail || 'Pilihan referensi tidak tersedia.');
            if (response.status === 422) throw new Error(detail || 'Pilihan belum valid. Periksa target, prioritas, dan alergi Anda.');
            if (response.status === 503) throw new Error(detail || 'Layanan rekomendasi atau database sementara tidak tersedia.');
            if (response.status === 404) throw new Error('Endpoint layanan tidak ditemukan. Periksa URL AI Backend.');
            throw new Error(detail || `Layanan rekomendasi sedang bermasalah (HTTP ${response.status}). Silakan coba lagi.`);
        }
        if (!body || typeof body !== 'object' || Array.isArray(body)) throw new Error('Respons layanan tidak dapat dibaca. Silakan coba lagi.');
        return body;
    } catch (error) {
        if (error.name === 'AbortError') throw new Error(`Permintaan terlalu lama (batas waktu ${REQUEST_TIMEOUT_MS / 1000} detik). Periksa koneksi dan kesiapan database.`);
        if (error instanceof TypeError) throw new Error('Tidak dapat terhubung ke AI Backend. Periksa alamat server, CORS, dan koneksi.');
        throw error;
    } finally { clearTimeout(timeout); }
}

function readState() { try { return JSON.parse(sessionStorage.getItem(KEY) || '{}'); } catch { return {}; } }
function saveState(state) { sessionStorage.setItem(KEY, JSON.stringify(state)); }
function element(tag, text, className) { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (className) el.className = className; return el; }
const choiceIcons = { rendah: '♨', sedang: 'ϟ', tinggi: '✦', protein: '✦', karbohidrat: '♧', lemak: '◉', seimbang: '⚖', telur: '◉', ikan: '♒', ayam: '✦', beras: '♧', 'daging sapi': '◈', 'kacang-kacangan': '❋', 'udang/seafood': '♒', gandum: '♧', kedelai: '❋', jagung: '♧', kelapa: '◉' };
const allergyIconPaths = {
    'daging sapi': 'M5 8c-2-2 1-5 4-4l2 2 3-1 4 3-1 4-3 2-5-1-4-3Z',
    telur: 'M12 3C8 3 5 9 5 14a7 7 0 0 0 14 0c0-5-3-11-7-11Z',
    'kacang-kacangan': 'M7 5c-3 2-3 12 2 14 4 2 10-3 10-8 0-5-7-9-12-6Z',
    ikan: 'M3 12c3-5 11-7 16 0-5 7-13 5-16 0Zm16 0 3-4v8l-3-4ZM10 10h.1',
    'udang/seafood': 'M5 7c4-4 11-2 12 3 1 5-4 8-9 6L5 13l-2-3 2-3Zm12 3 4-3v8l-4-3M7 17l-2 3M11 18l-1 3',
    gandum: 'M12 21V3M12 8C7 8 5 6 5 3c4 0 7 2 7 5ZM12 13C7 13 4 11 4 8c5 0 8 2 8 5ZM12 18C7 18 4 16 4 13c5 0 8 2 8 5ZM12 8c5 0 7-2 7-5-4 0-7 2-7 5ZM12 13c5 0 8-2 8-5-5 0-8 2-8 5ZM12 18c5 0 8-2 8-5-5 0-8 2-8 5Z',
    kedelai: 'M6 5c-3 3-2 10 2 13 4 3 10 0 10-5 0-5-7-11-12-8Z',
    jagung: 'M8 4c-3 3-3 13 4 16 7-3 7-13 4-16-2-2-6-2-8 0ZM8 8l8 8M8 13l6 6M16 8l-8 8',
    kelapa: 'M12 3C8 3 4 7 4 13a8 8 0 0 0 16 0c0-6-4-10-8-10ZM8 14c0 2 2 4 4 4',
    beras: 'M12 21V4M12 9C7 9 6 6 6 4c4 0 6 2 6 5ZM12 14C7 14 5 11 5 9c5 0 7 2 7 5ZM12 9c5 0 6-3 6-5-4 0-6 2-6 5ZM12 14c5 0 7-3 7-5-5 0-7 2-7 5Z',
    ayam: 'M8 5c2-2 5-1 6 1l2 2 3 1 2 4-3 3-4-1-3 2-5-2-2-4 2-4Z'
};
const priorityIconPaths = {
    protein: 'M8 4c3-2 6 1 5 4l5 5c3-1 6 2 4 5-1 3-4 3-6 1-2 2-5 1-5-2l-5-5C2 13 0 10 2 7c1-3 4-4 6-3Z',
    karbohidrat: 'M12 21V3M12 8C7 8 5 6 5 3c4 0 7 2 7 5ZM12 13C7 13 4 11 4 8c5 0 8 2 8 5ZM12 18C7 18 4 16 4 13c5 0 8 2 8 5ZM12 8c5 0 7-2 7-5-4 0-7 2-7 5ZM12 13c5 0 8-2 8-5-5 0-8 2-8 5ZM12 18c5 0 8-2 8-5-5 0-8 2-8 5Z',
    lemak: 'M12 2C9 7 4 11 4 16a8 8 0 0 0 16 0c0-5-5-9-8-14ZM8 16c0 2 1 3 3 4',
    seimbang: 'M12 3v18M7 21h10M4 7h16M6 7l-4 8h8L6 7ZM18 7l-4 8h8l-4-8Z'
};

async function setupChoices(formId, containerId, field, apiField, idField, labelField, type) {
    const form = document.getElementById(formId);
    const container = document.getElementById(containerId);
    const submit = document.querySelector(`button[form="${formId}"]`) || form.querySelector('button[type="submit"]');
    if (!form || !container || !submit) return;
    const notice = element('p', 'Memuat pilihan dari layanan…');

notice.setAttribute('role', 'status');

if (type !== 'checkbox') {
    container.before(notice);
}
    submit.disabled = true;
    container.replaceChildren();
    const retry = element('button', 'Coba lagi', 'btn-back');
    retry.type = 'button'; retry.hidden = true; notice.after(retry);
    const loading = element('div', undefined, 'request-spinner');
    loading.setAttribute('role', 'status'); loading.setAttribute('aria-label', 'Memuat pilihan');
    notice.before(loading);
    async function load() {
        retry.hidden = true; loading.hidden = false; submit.disabled = true; notice.textContent = 'Memuat pilihan dari layanan…';
        try {
            const data = await requestApi('/api/v1/reference-data');
            if (!Array.isArray(data[apiField]) || !data[apiField].length) throw new Error('Pilihan belum tersedia.');
            container.replaceChildren();
            const state = readState();
            const allergyOrder = ['daging sapi', 'telur', 'kacang-kacangan', 'ikan', 'udang/seafood', 'gandum', 'kedelai', 'jagung', 'kelapa', 'beras', 'ayam'];
            const items = apiField === 'alergen'
                ? [...data[apiField]].sort((a, b) => {
                    const indexA = allergyOrder.indexOf(a[labelField].toLowerCase());
                    const indexB = allergyOrder.indexOf(b[labelField].toLowerCase());
                    return (indexA < 0 ? allergyOrder.length : indexA) - (indexB < 0 ? allergyOrder.length : indexB);
                })
                : data[apiField];
            for (const item of items) {
                if (!Number.isInteger(item[idField]) || item[idField] <= 0 || typeof item[labelField] !== 'string') throw new Error('Data pilihan tidak valid.');
                const label = element('label', undefined, `choice${type === 'checkbox' ? ' allergy-choice' : ''}`);
                const input = element('input'); input.type = type; input.name = field; input.value = String(item[idField]); input.dataset.label = item[labelField];
                if (type === 'checkbox') input.setAttribute('aria-label', item[labelField]);
                input.checked = type === 'checkbox' ? (state.alergen || []).some(x => x.id === item[idField]) : state[field]?.id === item[idField];
                const icon = choiceIcons[item[labelField].toLowerCase()] || '✦';
                const indicator = element(
    'span',
    type === 'checkbox' ? '✓' : (input.checked ? '✓' : ''),
    'radio'
);
                const itemKey = item[labelField].toLowerCase();

const iconDisc = element('div', '', 'icon-disc');

if (apiField === 'alergen' && allergyIconPaths[itemKey]) {
    iconDisc.innerHTML = `
        <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="${allergyIconPaths[itemKey]}"></path>
        </svg>
    `;
} else {
    iconDisc.textContent = icon;
}

                iconDisc.setAttribute('aria-hidden', 'true');
                const title = element('strong', item[labelField]);
                label.append(input, iconDisc, title);

const description = item.keterangan;
if (description) {
    label.append(

        element('span', description, 'description')
    );
}

                label.append(indicator);
                container.append(label);
                if (type === 'radio') {
    container.addEventListener('change', () => {
        container.querySelectorAll('.choice').forEach(card => {
            const radioInput = card.querySelector('input');
            const radioIndicator = card.querySelector('.radio');

            if (radioIndicator) {
                radioIndicator.textContent = radioInput.checked ? '✓' : '';
            }
        });
    });
}
            }
            loading.hidden = true;
            notice.textContent = '';
            if (type === 'checkbox') {
                const updateSelection = () => {
                    const count = container.querySelectorAll('input:checked').length;
                    notice.textContent = count ? `${count} bahan dipilih.` : 'Pilih minimal satu bahan untuk melanjutkan.';
                    submit.disabled = count === 0;
                    const countDisplay = document.getElementById('allergy-selection-count');
                    if (countDisplay) countDisplay.textContent = notice.textContent;
                };
                container.onchange = updateSelection;
                updateSelection();
            } else {
                submit.disabled = false;
            }
        } catch (error) { loading.hidden = true; notice.textContent = `${error.message} `; retry.hidden = false; }
    }
    retry.addEventListener('click', load);
    form.addEventListener('submit', event => {
        event.preventDefault();
        const selected = [...container.querySelectorAll('input:checked')];
        if (!selected.length) { notice.textContent = 'Pilih setidaknya satu pilihan untuk melanjutkan.'; return; }
        const state = readState();
        const values = selected.map(input => ({ id: Number(input.value), label: input.dataset.label }));
        if (type === 'checkbox') {
            state.alergen = values; state.status_alergi = true;
            const calorieField = form.querySelector('#selected-calorie');
            const priorityField = form.querySelector('#selected-priority');
            if (calorieField) calorieField.value = String(state.target?.id || '');
            if (priorityField) priorityField.value = String(state.prioritas?.id || '');
        }
        else {
            state[field] = values[0];
            const fieldTarget = form.querySelector(field === 'target' ? '#selected-calorie' : '#selected-priority');
            if (fieldTarget) fieldTarget.value = String(values[0].id);
        }
        delete state.result; saveState(state);
        location.assign(form.action);
    }, true);
    await load();
}

function setupAllergy() {
    const buttons = document.querySelectorAll('.allergy-question-buttons a');
    buttons.forEach((button, index) => button.addEventListener('click', event => {
        event.preventDefault(); const state = readState(); state.status_alergi = index === 0;
        if (!state.status_alergi) state.alergen = [];
        delete state.result; saveState(state);
        const destination = index === 0 ? '/daftaralergi' : '/rekomendasi';
        const query = new URLSearchParams({ kalori: state.target?.id || '', prioritas: state.prioritas?.id || '', alergi: state.status_alergi ? 'ya' : 'tidak' });
        location.assign(`${destination}?${query}`);
    }));
}

async function submitRecommendation() {
    const errorBox = document.getElementById('request-error');
    const loading = document.getElementById('recommendation-spinner');
    let busy = false;
    async function send() {
        if (busy) return;
        busy = true; errorBox.replaceChildren();
        document.querySelector('.screen-loading .status-box').hidden = false;
        loading.hidden = false;
        const state = readState(); delete state.result; saveState(state);
        try {
            const payload = makePayload(state);
            const response = await requestApi('/api/v1/recommendations/content-based', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
            if (!Array.isArray(response.kandidat) || response.kandidat.length > 3 || response.jumlah_kandidat !== response.kandidat.length || response.kandidat.some(item => typeof item.nama_makanan !== 'string' || typeof item.deskripsi_porsi !== 'string' || !['kalori', 'protein', 'karbohidrat', 'lemak', 'skor_content_based'].every(key => Number.isFinite(Number(item[key]))))) throw new Error('Struktur respons rekomendasi tidak sesuai dengan kontrak AI Backend.');
            state.result = response; saveState(state); location.replace('/hasil');
        } catch (error) {
            document.querySelector('.screen-loading .status-box').hidden = true;
            loading.hidden = true;
            errorBox.append(element('p', error.message));
            const retry = element('button', 'Coba lagi', 'btn-next'); retry.type = 'button'; retry.addEventListener('click', send);
            const edit = element('a', 'Ubah kebutuhan', 'btn-back'); edit.href = '/kalori'; errorBox.append(retry, edit);
        } finally { busy = false; }
    }
    await send();
}

function showEmptyState() {
    const state = readState();
    const summary = document.getElementById('empty-summary');
    const message = document.getElementById('empty-message');
    if (message && state.result?.pesan_kosong) message.textContent = state.result.pesan_kosong;
    if (summary) {
        for (const text of [`Kalori: ${state.target?.label || '-'}`, `Prioritas: ${state.prioritas?.label || '-'}`, `Alergi: ${state.status_alergi ? (state.alergen || []).map(x => x.label).join(', ') : 'Tidak ada'}`]) summary.append(element('span', text));
    }
}

function showResult() {
    const state = readState(); const result = state.result;
    if (!result || !Array.isArray(result.kandidat)) {
        location.replace('/kalori');
        return;
    }
    if (result.kandidat.length === 0) {
        location.replace('/tidakditemukan');
        return;
    }
    const message = document.getElementById('result-message');
    const summary = document.getElementById('result-summary');
    for (const text of [`Kalori: ${state.target?.label || '-'}`, `Prioritas: ${state.prioritas?.label || '-'}`, `Alergi: ${state.status_alergi ? (state.alergen || []).map(x => x.label).join(', ') : 'Tidak ada'}`]) summary.append(element('span', text));
    if (!result.kandidat.length) message.textContent = result.pesan_kosong || 'Tidak ada makanan yang lolos penyaringan.';
    const grid = document.getElementById('result-grid');
    const urutanTampilan = result.kandidat.length === 3
        ? [result.kandidat[1], result.kandidat[0], result.kandidat[2]]
        : result.kandidat;

    urutanTampilan.forEach(item => {
        const peringkatAsli = result.kandidat.indexOf(item) + 1;
        const card = element(
            'article',
            undefined,
            `food-card${peringkatAsli === 1 ? ' best-match' : ''}`
        );
        card.append(element('div', String(peringkatAsli), 'food-rank'));
        if (peringkatAsli === 1) {
            card.append(element('span', 'REKOMENDASI TERBAIK', 'best-label'));
        }
        card.append(element('h2', item.nama_makanan), element('p', `${item.deskripsi_porsi}${item.berat_porsi_gram == null ? '' : ` (${item.berat_porsi_gram} g)`}`));
        const nutrition = element('div', undefined, 'food-nutrition');
        for (const [name, value, unit] of [['Kalori', item.kalori, 'kkal'], ['Protein', item.protein, 'g'], ['Karbohidrat', item.karbohidrat, 'g'], ['Lemak', item.lemak, 'g']]) {
            const row = element('div'); row.append(element('span', name), element('strong', `${value} ${unit}`)); nutrition.append(row);
        }
        card.append(nutrition, element('p', `Skor content-based: ${Number(item.skor_content_based).toFixed(2)} / 100`, 'match-label'));
        grid.append(card);
    });
}

if (typeof document !== 'undefined') {
    const path = location.pathname.replace(/\/$/, '') || '/';
    if (path === '/') sessionStorage.removeItem(KEY);
    document.querySelectorAll('[data-clear-session]').forEach(link => {
        link.addEventListener('click', () => {
            sessionStorage.removeItem(KEY);
            document.getElementById('result-summary')?.replaceChildren();
            document.getElementById('result-grid')?.replaceChildren();
            document.getElementById('empty-summary')?.replaceChildren();
        });
    });
    if (path === '/kalori') setupChoices('calorieForm', 'calorieOptions', 'target', 'target_kalori', 'id_target', 'nama_kategori', 'radio');
    if (path === '/prioritas') setupChoices('priorityForm', 'priorityOptions', 'prioritas', 'prioritas_nutrisi', 'id_prioritas', 'nama_prioritas', 'radio');
    if (path === '/alergi') setupAllergy();
    if (path === '/daftaralergi') setupChoices('allergyForm', 'allergyOptions', 'alergi[]', 'alergen', 'id_alergen', 'nama_alergen', 'checkbox');
    if (path === '/rekomendasi') submitRecommendation();
    if (path === '/hasil') showResult();
    if (path === '/tidakditemukan') showEmptyState();
    if (path === '/gangguan') {
        document.getElementById('retry-recommendation')?.addEventListener('click', () => location.assign('/rekomendasi'));
    }
}

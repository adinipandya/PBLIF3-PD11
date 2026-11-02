const API = (import.meta.env?.VITE_NUTRIREC_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
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
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
        const response = await fetcher(`${API}${path}`, { ...options, signal: controller.signal });
        let body = null;
        try { body = await response.json(); } catch { /* Server may return non-JSON errors. */ }
        if (!response.ok) {
            if (response.status === 400) throw new Error(typeof body?.detail === 'string' ? body.detail : 'Pilihan referensi tidak tersedia.');
            if (response.status === 422) throw new Error('Pilihan belum valid. Periksa target, prioritas, dan alergi Anda.');
            throw new Error('Layanan rekomendasi sedang bermasalah. Silakan coba lagi.');
        }
        if (!body || typeof body !== 'object') throw new Error('Respons layanan tidak dapat dibaca. Silakan coba lagi.');
        return body;
    } catch (error) {
        if (error.name === 'AbortError') throw new Error('Permintaan terlalu lama. Periksa koneksi dan coba lagi.');
        if (error instanceof TypeError) throw new Error('Tidak dapat terhubung ke layanan. Periksa koneksi dan coba lagi.');
        throw error;
    } finally { clearTimeout(timeout); }
}

function readState() { try { return JSON.parse(sessionStorage.getItem(KEY) || '{}'); } catch { return {}; } }
function saveState(state) { sessionStorage.setItem(KEY, JSON.stringify(state)); }
function element(tag, text, className) { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (className) el.className = className; return el; }
const choiceIcons = { rendah: '♨', sedang: 'ϟ', tinggi: '✦', protein: '✦', karbohidrat: '♧', lemak: '◉', seimbang: '⚖', telur: '◉', ikan: '♒', ayam: '✦', beras: '♧' };

async function setupChoices(formId, containerId, field, apiField, idField, labelField, type) {
    const form = document.getElementById(formId);
    const container = document.getElementById(containerId);
    const submit = form.querySelector('button[type="submit"]');
    const notice = element('p', 'Memuat pilihan dari layanan…');
    notice.setAttribute('role', 'status');
    container.before(notice);
    submit.disabled = true;
    container.replaceChildren();
    const retry = element('button', 'Coba lagi', 'btn-back');
    retry.type = 'button'; retry.hidden = true; notice.after(retry);
    async function load() {
        retry.hidden = true; submit.disabled = true; notice.textContent = 'Memuat pilihan dari layanan…';
        try {
            const data = await requestApi('/api/v1/reference-data');
            if (!Array.isArray(data[apiField]) || !data[apiField].length) throw new Error('Pilihan belum tersedia.');
            container.replaceChildren();
            const state = readState();
            for (const item of data[apiField]) {
                if (!Number.isInteger(item[idField]) || item[idField] <= 0 || typeof item[labelField] !== 'string') throw new Error('Data pilihan tidak valid.');
                const label = element('label', undefined, `calorie-card${type === 'checkbox' ? ' allergy-card' : ''}`);
                const input = element('input'); input.type = type; input.name = field; input.value = String(item[idField]); input.dataset.label = item[labelField];
                input.checked = type === 'checkbox' ? (state.alergen || []).some(x => x.id === item[idField]) : state[field]?.id === item[idField];
                const icon = choiceIcons[item[labelField].toLowerCase()] || '✦';
                const indicator = element('span', '✓', 'choice-check'); indicator.setAttribute('aria-hidden', 'true');
                label.append(input, element('div', icon, 'calorie-icon'), element('h3', item[labelField]));
                if (item.keterangan) label.append(element('p', item.keterangan));
                label.append(indicator);
                container.append(label);
            }
            notice.textContent = ''; submit.disabled = false;
        } catch (error) { notice.textContent = `${error.message} `; retry.hidden = false; }
    }
    retry.addEventListener('click', load);
    form.addEventListener('submit', event => {
        event.preventDefault();
        const selected = [...container.querySelectorAll('input:checked')];
        if (!selected.length) { notice.textContent = 'Pilih setidaknya satu pilihan untuk melanjutkan.'; return; }
        const state = readState();
        const values = selected.map(input => ({ id: Number(input.value), label: input.dataset.label }));
        if (type === 'checkbox') { state.alergen = values; state.status_alergi = true; }
        else state[field] = values[0];
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
        delete state.result; saveState(state); location.assign(index === 0 ? '/daftaralergi' : '/rekomendasi');
    }));
}

async function submitRecommendation() {
    const errorBox = document.getElementById('request-error');
    let busy = false;
    async function send() {
        if (busy) return;
        busy = true; errorBox.replaceChildren();
        document.querySelector('.loading-content').hidden = false;
        const state = readState(); delete state.result; saveState(state);
        try {
            const payload = makePayload(state);
            const response = await requestApi('/api/v1/recommendations/content-based', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
            if (!Array.isArray(response.kandidat) || response.kandidat.length > 3) throw new Error('Respons rekomendasi tidak valid.');
            state.result = response; saveState(state); location.replace('/hasil');
        } catch (error) {
            document.querySelector('.loading-content').hidden = true;
            errorBox.append(element('p', error.message));
            const retry = element('button', 'Coba lagi', 'btn-next'); retry.type = 'button'; retry.addEventListener('click', send);
            const edit = element('a', 'Ubah kebutuhan', 'btn-back'); edit.href = '/kalori'; errorBox.append(retry, edit);
        } finally { busy = false; }
    }
    await send();
}

function showResult() {
    const state = readState(); const result = state.result;
    const message = document.getElementById('result-message');
    if (!result || !Array.isArray(result.kandidat)) { message.textContent = 'Belum ada hasil. Silakan isi kebutuhan Anda.'; return; }
    const summary = document.getElementById('result-summary');
    for (const text of [`Kalori: ${state.target?.label || '-'}`, `Prioritas: ${state.prioritas?.label || '-'}`, `Alergi: ${state.status_alergi ? (state.alergen || []).map(x => x.label).join(', ') : 'Tidak ada'}`]) summary.append(element('span', text));
    if (!result.kandidat.length) message.textContent = result.pesan_kosong || 'Tidak ada makanan yang lolos penyaringan.';
    const grid = document.getElementById('result-grid');
    result.kandidat.forEach((item, i) => {
        const card = element('article', undefined, 'food-card');
        card.append(element('div', String(i + 1), 'food-rank'), element('h2', item.nama_makanan), element('p', `${item.deskripsi_porsi}${item.berat_porsi_gram == null ? '' : ` (${item.berat_porsi_gram} g)`}`));
        const nutrition = element('div', undefined, 'food-nutrition');
        for (const [name, value, unit] of [['Kalori', item.kalori, 'kkal'], ['Protein', item.protein, 'g'], ['Karbohidrat', item.karbohidrat, 'g'], ['Lemak', item.lemak, 'g']]) {
            const row = element('div'); row.append(element('span', name), element('strong', `${value} ${unit}`)); nutrition.append(row);
        }
        card.append(nutrition, element('p', `Skor content-based: ${Number(item.skor_content_based).toFixed(2)} / 100`, 'match-label')); grid.append(card);
    });
}

if (typeof document !== 'undefined') {
    const path = location.pathname.replace(/\/$/, '') || '/';
    if (path === '/kalori') setupChoices('calorieForm', 'calorieOptions', 'target', 'target_kalori', 'id_target', 'nama_kategori', 'radio');
    if (path === '/prioritas') setupChoices('priorityForm', 'priorityOptions', 'prioritas', 'prioritas_nutrisi', 'id_prioritas', 'nama_prioritas', 'radio');
    if (path === '/alergi') setupAllergy();
    if (path === '/daftaralergi') setupChoices('allergyForm', 'allergyOptions', 'alergi[]', 'alergen', 'id_alergen', 'nama_alergen', 'checkbox');
    if (path === '/rekomendasi') submitRecommendation();
    if (path === '/hasil') showResult();
}

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { makePayload, requestApi } from '../resources/js/app.js';

const state = { target: { id: 12 }, prioritas: { id: 34 }, status_alergi: false, alergen: [{ id: 56 }] };

test('payload memakai ID referensi dan mengosongkan alergen saat tidak alergi', () => {
    assert.deepEqual(makePayload(state), { target_kalori_id: 12, prioritas_id: 34, status_alergi: false, alergen_ids: [] });
    assert.deepEqual(makePayload({ ...state, status_alergi: true }).alergen_ids, [56]);
    assert.throws(() => makePayload({ ...state, status_alergi: true, alergen: [] }));
    assert.throws(() => makePayload({ ...state, target: { id: 0 } }));
});

test('respons kosong dan kesalahan domain maupun internal ditangani', async () => {
    const result = await requestApi('/test', {}, async () => ({ ok: true, json: async () => ({ kandidat: [], pesan_kosong: 'kosong' }) }));
    assert.equal(result.pesan_kosong, 'kosong');
    await assert.rejects(requestApi('/test', {}, async () => ({ ok: false, status: 400, json: async () => ({ detail: 'Referensi tidak tersedia' }) })), /Referensi tidak tersedia/);
    await assert.rejects(requestApi('/test', {}, async () => ({ ok: false, status: 422, json: async () => ({ detail: [{}] }) })), /belum valid/);
    await assert.rejects(requestApi('/test', {}, async () => ({ ok: false, status: 500, json: async () => { throw new Error('not JSON'); } })), /sedang bermasalah/);
    await assert.rejects(requestApi('/test', {}, async () => { throw new TypeError('network'); }), /terhubung/);
});

test('timeout menampilkan pesan yang mudah dipahami', async () => {
    await assert.rejects(requestApi('/test', {}, async () => {
        const error = new Error('abort');
        error.name = 'AbortError';
        throw error;
    }), /terlalu lama/);
});

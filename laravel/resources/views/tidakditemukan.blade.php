
@extends('layouts.app')
@section('title', 'Rekomendasi Tidak Ditemukan - NutriRec AI')
@section('status', 'Rekomendasi tidak ditemukan')
@section('body-class', 'notfound-page')
@section('content')
    <main class="screen-content screen-empty">
        <section class="content status-box notfound-card">

            <!-- Ikon piring dan alat makan -->
            <div class="notfound-icon">
                <svg viewBox="0 0 64 64" fill="none">
                    <circle cx="32" cy="32" r="21" stroke="#FDAF00" stroke-width="3"/>
                    <circle cx="32" cy="32" r="15.5" stroke="#D8CDB8" stroke-width="2" stroke-dasharray="3 3"/>

                    <circle cx="29" cy="30" r="5" stroke="#AFA99F" stroke-width="2"/>
                    <path d="M32.5 33.5L37 38" stroke="#AFA99F" stroke-width="2.5" stroke-linecap="round"/>
                    <path d="M27 28L31 32M31 28L27 32" stroke="#AFA99F" stroke-width="1.3" stroke-linecap="round"/>

                    <path d="M5 10V22M9 10V22M13 10V22M9 22V51" stroke="#15172B" stroke-width="2.5" stroke-linecap="round"/>
                    <path d="M5 10V17C5 20 7 22 9 22C11 22 13 20 13 17V10" stroke="#15172B" stroke-width="2" stroke-linecap="round"/>

                    <path d="M55 10C55 10 51 15 51 22V28H55V51" stroke="#15172B" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </div>

            <header class="question-header">
            <h1 class="heading">Rekomendasi Tidak Ditemukan</h1>
            <p id="empty-message" class="body-copy" role="status">Belum ada makanan yang sesuai dengan kriteria Anda. Silakan ubah pilihan untuk mendapatkan rekomendasi lain.</p>
            </header>

            <!-- Informasi pilihan pengguna -->
            <div class="notfound-info">

                <div id="empty-summary" class="notfound-info result-info" aria-label="Ringkasan pilihan"></div>

            </div>

            <nav class="actions screen-actions" aria-label="Navigasi hasil kosong">
                <a href="{{ url('/kalori') }}" class="secondary">Personalisasi Ulang</a>
                <a href="{{ url('/') }}" class="primary" data-clear-session>Selesai <span aria-hidden="true">→</span></a>
            </nav>

        </section>

    </main>

@endsection

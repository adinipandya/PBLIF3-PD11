@extends('layouts.app')
@section('title', 'Hasil Rekomendasi - NutriRec AI')
@section('status', 'Rekomendasi content-based')
@section('body-class', 'result-page')
@section('content')
    <div class="screen-content screen-result">
        <section class="content results-screen">
            <header class="question-header result-heading">
                <span class="eyebrow">HASIL REKOMENDASI</span>
                <h1 class="heading">Hasil Rekomendasi</h1>
                <div id="result-summary" class="chips"></div>
            </header>
            <p id="result-message" role="status"></p>
            <section id="result-grid" class="result-grid"></section>
            <p class="notice">Skor content-based bukan probabilitas atau jaminan keamanan alergi. Periksa bahan makanan dengan penyedia.</p>
            <nav class="actions result-action screen-actions" aria-label="Navigasi hasil">
                <a href="{{ url('/kalori') }}" class="secondary">Personalisasi Ulang</a>
                <a href="{{ url('/') }}" class="primary" data-clear-session>Selesai <span aria-hidden="true">→</span></a>
            </nav>
        </section>
    </div>
@endsection
~
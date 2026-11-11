
@extends('layouts.app')
@section('title', 'NutriRec AI - Personalisasi Nutrisi')
@section('content')
<main class="screen-content screen-welcome">
    <section class="welcome content">
        <header class="question-header">
            <h1 class="heading">Personalisasi Nutrisi Anda Secara Instan</h1>
            <p class="body-copy">Temukan makanan sesuai kebutuhan gizi Anda.</p>
        </header>
        <a href="{{ url('/kalori') }}" class="primary">Mulai Personalisasi <span aria-hidden="true">→</span></a>
        <section class="steps-panel">
            <span class="small">TAHAPAN CEPAT</span>
            <h2>CARA KERJA</h2>
            <div class="steps-grid">
                <div class="step"><span class="step-number">1</span>Pilih target kalori</div>
                <div class="step"><span class="step-number">2</span>Tentukan prioritas nutrisi</div>
                <div class="step"><span class="step-number">3</span>Pilih alergi</div>
                <div class="step"><span class="step-number">4</span>Dapatkan Top 3 rekomendasi</div>
            </div>
        </section>
    </section>
</main>
@endsection

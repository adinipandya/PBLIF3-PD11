
@extends('layouts.app')
@section('title', 'Alergi - NutriRec AI')
@section('content')
<main class="screen-content screen-allergy-question">
    <section class="content">
        <header class="question-header">
            <span class="eyebrow">LANGKAH 3 DARI 3 • ALERGI</span>
            <h1 class="heading">Apakah Anda memiliki alergi makanan?</h1>
        </header>

        <div class="gate allergy-question-buttons">
            <a href="{{ url('/daftaralergi') }}" class="primary">Memiliki Alergi</a>
            <a href="{{ url('/rekomendasi') }}?alergi=tidak" class="secondary">Tidak Memiliki Alergi</a>
        </div>
    </section>
</main>
@endsection

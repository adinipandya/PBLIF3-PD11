
@extends('layouts.app')
@section('title', 'Pilih Alergi - NutriRec AI')
@section('content')
<main class="screen-content screen-allergy">
    <section class="content">
        <header class="question-header">
            <span class="eyebrow">LANGKAH 3 DARI 3 • ALERGI</span>
            <h1 class="heading">Bahan makanan apa yang membuat Anda alergi?</h1>
            <p class="body-copy">Pilih semua bahan yang perlu Anda hindari. Ketuk lagi untuk membatalkan pilihan.</p>
        </header>

        <section class="choices allergy-choices">

            <form action="{{ url('/rekomendasi') }}" method="GET" id="allergyForm">
                <input type="hidden" name="kalori" id="selected-calorie" value="{{ request('kalori') }}">
                <input type="hidden" name="prioritas" id="selected-priority" value="{{ request('prioritas') }}">

                <div class="calorie-options allergy-grid allergy-choices" id="allergyOptions"></div>

                <p id="allergy-selection-count" class="notice" role="status"></p>

            </form>
            <button type="submit" form="allergyForm" class="primary screen-action" disabled>Lanjut <span aria-hidden="true">→</span></button>

        </section>
    </section>
</main>
@endsection

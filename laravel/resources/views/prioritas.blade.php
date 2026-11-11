
@extends('layouts.app')
@section('title', 'Prioritas Nutrisi - NutriRec AI')
@section('content')
<main class="screen-content screen-priority">
    <section class="content">
        <header class="question-header">
            <span class="eyebrow">LANGKAH 2 DARI 3 • PRIORITAS NUTRISI</span>
            <h1 class="heading">Nutrisi apa yang jadi prioritas Anda?</h1>
        </header>

        <!-- PRIORITY SELECTION -->
        <section class="choices nutrition choices-nutrition">

            <form action="{{ url('/alergi') }}" method="GET" id="priorityForm">

                <input type="hidden" name="kalori" id="selected-calorie" value="{{ request('kalori') }}">
                <input type="hidden" name="prioritas" id="selected-priority" value="{{ request('prioritas') }}">

                <div class="calorie-options priority-options choices nutrition" id="priorityOptions"></div>

            </form>

</section>

        </section>
    </section>
</main>
@endsection

@section('actions')
<button type="submit" form="priorityForm" class="primary screen-action" disabled>
    Lanjut <span aria-hidden="true">→</span>
</button>
@endsection

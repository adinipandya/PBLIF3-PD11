
@extends('layouts.app')

@section('title', 'Target Kalori - NutriRec AI')

@section('content')

<main class="screen-content screen-calorie">

    <section class="content">

        <header class="question-header">

            <span class="eyebrow">
                LANGKAH 1 DARI 3 • TARGET KALORI
            </span>

            <h1 class="heading">
                Berapa target kalori Anda?
            </h1>

        </header>

        <!-- FORM TARGET KALORI -->
        <form action="{{ url('/prioritas') }}"
              method="GET"
              id="calorieForm">

            <input
                type="hidden"
                name="kalori"
                id="selected-calorie"
                value="{{ request('kalori') }}"
            >

            <!-- CARD DIBUAT OTOMATIS DARI API -->
            <div
                class="calorie-options choices"
                id="calorieOptions">
            </div>

        </form>

    </section>

</main>

@endsection


@section('actions')

<button
    type="submit"
    form="calorieForm"
    class="primary screen-action"
    disabled
>
    Lanjut <span aria-hidden="true">→</span>
</button>

@endsection

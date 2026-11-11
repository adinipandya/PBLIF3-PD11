@extends('layouts.app')
@section('title', 'Menyiapkan Rekomendasi - NutriRec AI')
@section('status', 'Pemrosesan content-based')
@section('body-class', 'loading-page')
@section('content')
    <main class="screen-content screen-loading">
        <section class="content status-box">
            <div class="status-icon" aria-hidden="true">⌛</div>
            <header class="question-header">
                <h1 class="heading">Menyiapkan Rekomendasi</h1>
                <p class="body-copy">Sedang mencari makanan yang cocok untuk Anda...</p>
            </header>
            <div id="recommendation-spinner" class="spinner" role="status" aria-label="Sedang memuat"></div>

        </section>
        <div id="request-error" role="alert" class="result-action"></div>
    </main>

@endsection

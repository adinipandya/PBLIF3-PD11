@extends('layouts.app')
@section('title', 'Gangguan Sistem - NutriRec AI')
@section('status', 'Sistem mengalami gangguan')
@section('body-class', 'error-page')
@section('content')
    <main class="screen-content screen-error">
        <section class="content status-box error-card">

            <div class="error-icon status-icon">
                <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M32 7L59 55H5L32 7Z" stroke="currentColor" stroke-width="3.5" stroke-linejoin="round"/>
                    <path d="M32 23V37" stroke="currentColor" stroke-width="4" stroke-linecap="round"/>
                    <circle cx="32" cy="46" r="2.5" fill="currentColor"/>
                </svg>
            </div>

            <header class="question-header">
            <h1 class="heading">Maaf, terjadi gangguan pada sistem. Silakan coba lagi.</h1>

            <p class="body-copy error-description">
                Koneksi ke server pusat NUTRIREC-AI mengalami kendala sesaat.
                Silakan coba kembali beberapa saat lagi.
            </p>
            </header>

            <nav class="actions screen-actions" aria-label="Aksi pemulihan">
                <button type="button" class="primary" id="retry-recommendation">Coba Lagi</button>
                <a href="{{ url('/') }}" class="secondary">Selesai</a>
            </nav>

        </section>
    </main>

@endsection
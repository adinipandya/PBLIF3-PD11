<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hasil Rekomendasi - NutriRec AI</title>
    @vite(['resources/css/style.css', 'resources/js/app.js'])
</head>
<body class="result-page">
    <header class="navbar"><a href="{{ url('/') }}" class="logo">NutriRec <span>AI.</span></a><div class="nav-status">Rekomendasi content-based</div></header>
    <main class="result-main">
        <section class="result-heading"><span class="screen-step">HASIL REKOMENDASI</span><h1>Rekomendasi Makanan untuk Anda</h1><div id="result-summary" class="result-info"></div></section>
        <p id="result-message" role="status"></p>
        <section id="result-grid" class="result-grid"></section>
        <p>Skor content-based bukan probabilitas atau jaminan keamanan alergi. Periksa bahan makanan dengan penyedia.</p>
        <div class="result-action"><a href="{{ url('/kalori') }}" class="btn-back">Personalisasi Ulang</a> <a href="{{ url('/') }}" class="result-finish">Selesai →</a></div>
    </main>
    <footer class="footer">© 2026 NutriRec AI Kiosk. All rights reserved.</footer>
</body>
</html>
~
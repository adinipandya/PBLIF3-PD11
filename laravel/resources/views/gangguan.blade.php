<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gangguan Sistem - NutriRec AI</title>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Playfair+Display:wght@600;700;800&display=swap" rel="stylesheet">

    @vite('resources/css/style.css')
</head>
<body class="error-page">

    <header class="navbar">
        <a href="{{ url('/') }}" class="logo">NutriRec <span>AI.</span></a>

        <div class="nav-status status-error">
            <span class="status-dot"></span>
            Sistem Mengalami Gangguan
        </div>
    </header>

    <main class="error-main">
        <section class="error-card">

            <div class="error-icon">
                <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M32 7L59 55H5L32 7Z" stroke="currentColor" stroke-width="3.5" stroke-linejoin="round"/>
                    <path d="M32 23V37" stroke="currentColor" stroke-width="4" stroke-linecap="round"/>
                    <circle cx="32" cy="46" r="2.5" fill="currentColor"/>
                </svg>
            </div>

            <h1>Maaf, Terjadi Gangguan pada Sistem</h1>

            <p class="error-description">
                Koneksi ke server pusat NUTRIREC-AI mengalami kendala sesaat.
                Silakan coba kembali beberapa saat lagi.
            </p>

            <div class="error-actions">
                <a href="{{ url('/rekomendasi') }}" class="error-retry">
                    Coba Lagi
                </a>

                <a href="{{ url('/') }}" class="error-finish">
                    Kembali ke Beranda
                </a>
            </div>

        </section>
    </main>

    <footer class="footer">
        © 2026 NutriRec AI Kiosk. All rights reserved.
        <br>
        Informasi nutrisi disediakan untuk tujuan edukasi.
    </footer>

</body>
</html>
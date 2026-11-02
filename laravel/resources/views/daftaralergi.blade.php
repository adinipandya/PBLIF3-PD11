
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daftar Alergi - NutriRec AI</title>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Playfair+Display:wght@600;700;800&display=swap" rel="stylesheet">

    @vite(['resources/css/style.css', 'resources/js/app.js'])
</head>
<body>

    <header class="navbar">
        <a href="{{ url('/') }}" class="logo">
            NutriRec <span>AI.</span>
        </a>

        <div class="nav-status">
            <span class="status-dot"></span>
            Sistem Siap Digunakan
        </div>
    </header>

    <main class="main-content">

        <section class="hero">
            <h1>Bahan makanan apa yang membuat Anda alergi?</h1>
            <p>Pilih semua bahan yang perlu Anda hindari. Ketuk lagi untuk membatalkan pilihan.</p>
        </section>

        <section class="steps-container">

            <form action="{{ url('/rekomendasi') }}" method="GET" id="allergyForm">

                <input type="hidden" name="kalori" value="{{ request('kalori') }}">
                <input type="hidden" name="prioritas" value="{{ request('prioritas') }}">

                <div class="calorie-options allergy-grid" id="allergyOptions"></div>

                <div class="navigation-buttons allergy-submit">
                    <button type="submit" class="btn-next" disabled>
                        Lanjut →
                    </button>
                </div>

            </form>

        </section>

    </main>

    <footer class="footer">© 2026 NutriRec AI Kiosk. All rights reserved.</footer>



</body>
</html>

<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Menyiapkan Rekomendasi - NutriRec AI</title>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Playfair+Display:wght@600;700;800&display=swap" rel="stylesheet">

    @vite('resources/css/style.css')
</head>

<body class="loading-page">

    <header class="navbar">
    <div class="logo">NutriRec <span>AI.</span></div>

    <div class="nav-status status-loading">
        <span class="status-dot"></span>
        AI Sedang Memproses
    </div>
</header>

    <main class="loading-main">
        <div class="loading-content">

            <div class="loading-icon">
                <svg viewBox="0 0 24 24" fill="none"
                     stroke="currentColor" stroke-width="2"
                     stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 8c-3 0-5 3-5 7a5 5 0 0 0 10 0c0-4-2-7-5-7Z"/>
                    <path d="M12 8c-1-3 1-5 4-5"/>
                    <path d="M12 8c-2-2-4-2-5-1"/>
                </svg>
            </div>

            <h1>Menyiapkan Rekomendasi</h1>

            <p>Sedang mencari makanan yang cocok untuk Anda...</p>

            <div class="loading-dots">
                <span></span>
                <span></span>
                <span></span>
            </div>

        </div>
    </main>

    <footer class="footer">
    <div>© 2026 NutriRec AI Kiosk. All rights reserved.</div>
    <div>Informasi nutrisi disediakan untuk tujuan edukasi.</div>
</footer>
    <script>
        document.addEventListener('DOMContentLoaded', function () {
            setTimeout(function () {
                window.location.href = "{{ url('/hasil') }}";
            }, 3000);
        });
    </script>

</body>
</html>
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Menyiapkan Rekomendasi - NutriRec AI</title>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Playfair+Display:wght@600;700;800&display=swap" rel="stylesheet">

    @vite(['resources/css/style.css', 'resources/js/app.js'])
</head>

<body class="loading-page">

    <header class="navbar">
    <div class="logo">NutriRec <span>AI.</span></div>

    <div class="nav-status status-loading">
        <span class="status-dot"></span>
        Pemrosesan content-based
    </div>
</header>

    <main class="loading-main">
        <div class="loading-content">

            <h1>Menyiapkan Rekomendasi</h1>

            <p>Sedang mencari makanan yang cocok untuk Anda...</p>

            <div class="demo-spinner" role="status" aria-label="Sedang memuat"></div>

        </div>
        <div id="request-error" role="alert" class="result-action"></div>
    </main>

    <footer class="footer">© 2026 NutriRec AI Kiosk. All rights reserved.</footer>

</body>
</html>

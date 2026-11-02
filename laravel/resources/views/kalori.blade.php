
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Target Kalori - NutriRec AI</title>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Playfair+Display:wght@600;700;800&display=swap" rel="stylesheet">

    @vite(['resources/css/style.css', 'resources/js/app.js'])
</head>
<body>

    <!-- NAVBAR -->
    <header class="navbar">
        <a href="{{ url('/') }}" class="logo">
            NutriRec <span>AI.</span>
        </a>

        <div class="nav-status">
            <span class="status-dot"></span>
            Sistem Siap Digunakan
        </div>
    </header>

    <!-- MAIN CONTENT -->
    <main class="main-content">

        <section class="hero">
            <span class="screen-step">LANGKAH 1 DARI 3 • TARGET KALORI</span>
            <h1>Berapa target kalori Anda?</h1>
        </section>

        <!-- CALORIE SELECTION -->
        <section class="steps-container">

            <form action="{{ url('/prioritas') }}" method="GET" id="calorieForm">

                <div class="calorie-options" id="calorieOptions"></div>

                <!-- NAVIGATION BUTTONS -->
                <div class="navigation-buttons">
                    <button type="submit" class="btn-next" disabled>
                        Lanjut →
                    </button>
                </div>

            </form>

        </section>

    </main>

    <!-- FOOTER -->
    <footer class="footer">© 2026 NutriRec AI Kiosk. All rights reserved.</footer>

    <!-- VALIDATION -->


</body>
</html>

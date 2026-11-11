
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="theme-color" content="#fff9ef">

    <title>@yield('title', 'NutriRec AI')</title>

    @vite(['resources/css/style.css', 'resources/js/app.js'])
</head>

<body class="@yield('body-class')">
    <div class="app-shell">

        <!-- HEADER -->
        <header class="navbar">
            <a href="{{ url('/') }}" class="logo">
                NutriRec AI
            </a>
        </header>

        <!-- KONTEN HALAMAN -->
        <main class="page-body">
            @yield('content')
        </main>

        <!-- AREA TOMBOL NAVIGASI -->
        @hasSection('actions')
            <div class="actions screen-actions">
                @yield('actions')
            </div>
        @endif

        <!-- FOOTER -->
        <footer class="footer">
            2026 Kios AI NutriRec. Hak cipta dilindungi undang-undang.
        </footer>

    </div>
</body>
</html>

<?php

use Illuminate\Support\Facades\Route;

Route::get('/', function () {
    return view('welcome');
});

Route::get('/kalori', function () {
    return view('kalori');
});

Route::get('/prioritas', function () {
    return view('prioritas');
});

Route::get('/alergi', function () {
    return view('alergi');
});

Route::get('/daftaralergi', function () {
    return view('daftaralergi');
});

Route::redirect('/preferensi', '/kalori');

Route::get('/rekomendasi', function () {
    return view('rekomendasi');
});
Route::get('/hasil', function () {
    return view('hasil');
});
Route::get('/gangguan', function () {
    return view('gangguan');
});
Route::get('/tidakditemukan', function () {
    return view('tidakditemukan');
});
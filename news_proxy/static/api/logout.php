<?php
require __DIR__ . '/_bootstrap.php';
sx_session_start();

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    sx_json(['error' => 'Метод не поддерживается. Используйте POST.'], 405);
}

$_SESSION = [];
if (ini_get('session.use_cookies')) {
    $params = session_get_cookie_params();
    setcookie(session_name(), '', time()-42000, $params['path'], $params['domain'], $params['secure'], $params['httponly']);
}
session_destroy();

sx_json(['status'=>'ok']);

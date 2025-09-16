<?php
require __DIR__ . '/_bootstrap.php';
sx_session_start();

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    sx_json(['error' => 'Метод не поддерживается. Используйте POST.'], 405);
}

$d = sx_json_input();
$email = trim((string)($d['email'] ?? ''));
$pass  = (string)($d['password'] ?? '');

if ($email === '' || $pass === '') {
    sx_json(['error' => 'Заполните email и пароль.'], 400);
}
if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
    sx_json(['error' => 'Некорректный email.'], 400);
}

$users = sx_read_users();
$user = sx_find_user_by_email($users, $email);
if (!$user) {
    sx_json(['error' => 'Пользователь не найден.'], 404);
}

if (!password_verify($pass, $user['password_hash'])) {
    sx_json(['error' => 'Неверный пароль.'], 401);
}

// авторизация успешна
$_SESSION['uid'] = $user['id'];
sx_json(['status' => 'ok', 'uid' => $user['id']]);

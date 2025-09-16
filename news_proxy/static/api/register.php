<?php
require __DIR__ . '/_bootstrap.php';
sx_session_start();

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    sx_json(['error' => 'Метод не поддерживается. Используйте POST.'], 405);
}

$d = sx_json_input();
$name = trim((string)($d['name'] ?? ''));
$email = trim((string)($d['email'] ?? ''));
$pass  = (string)($d['password'] ?? '');

if ($name === '' || $email === '' || $pass === '') {
    sx_json(['error' => 'Заполните имя, email и пароль.'], 400);
}
if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
    sx_json(['error' => 'Некорректный email.'], 400);
}
if (strlen($pass) < 6) {
    sx_json(['error' => 'Пароль должен быть не короче 6 символов.'], 400);
}

$users = sx_read_users();
if (sx_find_user_by_email($users, $email)) {
    sx_json(['error' => 'Email уже зарегистрирован.'], 409);
}

$uid = sx_uuid();
$user = [
    'id' => $uid,
    'name' => $name,
    'email' => $email,
    'password_hash' => password_hash($pass, PASSWORD_DEFAULT),
    'role' => '',
    'location' => '',
    'lang' => 'kk',
    'avatar' => null,
    'created_at' => date('c')
];

$users[] = $user;
if (!sx_write_users($users)) {
    sx_json(['error' => 'Не удалось сохранить.'], 500);
}

$_SESSION['uid'] = $uid;
sx_json(['status' => 'ok', 'uid' => $uid]);

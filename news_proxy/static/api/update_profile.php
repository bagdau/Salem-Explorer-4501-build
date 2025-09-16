<?php
require __DIR__ . '/_bootstrap.php';
sx_session_start();
$me = sx_require_auth();

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    sx_json(['error' => 'Метод не поддерживается. Используйте POST.'], 405);
}

$d = sx_json_input();
$users = sx_read_users();
$idx = sx_find_user_index($users, $me['id']);
if ($idx < 0) sx_json(['error' => 'Пользователь не найден.'], 404);

// Allow fields
$allowed = ['name','email','role','location','lang','avatar'];
foreach ($allowed as $k) {
    if (array_key_exists($k, $d)) {
        if ($k === 'email') {
            $email = trim((string)$d[$k]);
            if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
                sx_json(['error' => 'Некорректный email.'], 400);
            }
            // unique check
            foreach ($users as $i => $u) {
                if ($i === $idx) continue;
                if (isset($u['email']) && mb_strtolower($u['email']) === mb_strtolower($email)) {
                    sx_json(['error' => 'Email уже занят.'], 409);
                }
            }
            $users[$idx][$k] = $email;
        } else {
            $users[$idx][$k] = $d[$k];
        }
    }
}

if (!sx_write_users($users)) {
    sx_json(['error' => 'Не удалось сохранить.'], 500);
}
$out = $users[$idx];
unset($out['password_hash']);
sx_json(['status'=>'ok','profile'=>$out]);

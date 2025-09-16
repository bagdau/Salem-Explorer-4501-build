<?php
require __DIR__ . '/_bootstrap.php';
sx_session_start();
$me = sx_require_auth();

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    sx_json(['error' => 'Метод не поддерживается. Используйте POST.'], 405);
}

if (!isset($_FILES['avatar']) || $_FILES['avatar']['error'] !== UPLOAD_ERR_OK) {
    sx_json(['error' => 'Файл не получен.'], 400);
}

$f = $_FILES['avatar'];
if ($f['size'] > 2*1024*1024) { // 2MB limit
    sx_json(['error' => 'Слишком большой файл (макс. 2MB).'], 400);
}

$allowed = ['image/jpeg'=>'jpg','image/png'=>'png','image/webp'=>'webp'];
$mime = mime_content_type($f['tmp_name']);
if (!isset($allowed[$mime])) {
    sx_json(['error' => 'Поддерживаются JPG, PNG, WEBP.'], 400);
}

$ext = $allowed[$mime];
$filename = $me['id'] . '_' . bin2hex(random_bytes(6)) . '.' . $ext;
$dest_dir = sx_avatars_dir();
$dest_path = $dest_dir . DIRECTORY_SEPARATOR . $filename;

// Move
if (!move_uploaded_file($f['tmp_name'], $dest_path)) {
    sx_json(['error' => 'Не удалось сохранить файл.'], 500);
}

// Public URL (assuming /UserData/ is web-served)
$public_url = '/UserData/avatars/' . rawurlencode($filename);

// Update user profile
$users = sx_read_users();
$idx = sx_find_user_index($users, $me['id']);
if ($idx >= 0) {
    $users[$idx]['avatar'] = $public_url;
    sx_write_users($users);
}

sx_json(['status'=>'ok','url'=>$public_url]);

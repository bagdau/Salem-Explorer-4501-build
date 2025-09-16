<?php
require __DIR__ . '/_bootstrap.php';

$user = sx_current_user();
if (!$user) {
    sx_json(['error' => 'Не авторизован.'], 401);
}

$out = $user;
unset($out['password_hash']);
sx_json($out);

<?php
// /api/_bootstrap.php — shared helpers for Salem Explorer account API
declare(strict_types=1);

// Timezone
date_default_timezone_set('Asia/Almaty');

// Security headers (minimal)
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: strict-origin-when-cross-origin');

// Start a secure session
function sx_session_start(): void {
    $secure = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off');
    session_set_cookie_params([
        'lifetime' => 60*60*24*7, // 7 days
        'path' => '/',
        'domain' => '',
        'secure' => $secure,
        'httponly' => true,
        'samesite' => 'Lax',
    ]);
    if (session_status() !== PHP_SESSION_ACTIVE) {
        session_start();
    }
}

// Paths
function sx_storage_dir(): string {
    // /api/.. => project root; store in /UserData
    $root = realpath(__DIR__ . '/..');
    $dir = $root . DIRECTORY_SEPARATOR . 'UserData';
    if (!is_dir($dir)) { @mkdir($dir, 0775, true); }
    return $dir;
}

function sx_avatars_dir(): string {
    $dir = sx_storage_dir() . DIRECTORY_SEPARATOR . 'avatars';
    if (!is_dir($dir)) { @mkdir($dir, 0775, true); }
    return $dir;
}

function sx_users_path(): string {
    return sx_storage_dir() . DIRECTORY_SEPARATOR . 'users.json';
}

// JSON I/O
function sx_read_users(): array {
    $file = sx_users_path();
    if (!file_exists($file)) return [];
    $fp = fopen($file, 'r');
    if ($fp === false) return [];
    flock($fp, LOCK_SH);
    $json = stream_get_contents($fp);
    flock($fp, LOCK_UN);
    fclose($fp);
    $data = json_decode($json ?: '[]', true);
    return is_array($data) ? $data : [];
}

function sx_write_users(array $users): bool {
    $file = sx_users_path();
    $tmp = $file . '.tmp';
    $json = json_encode($users, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);
    $fp = fopen($tmp, 'w');
    if ($fp === false) return false;
    if (!flock($fp, LOCK_EX)) { fclose($fp); return false; }
    fwrite($fp, $json);
    fflush($fp);
    flock($fp, LOCK_UN);
    fclose($fp);
    return rename($tmp, $file);
}

function sx_json_input(): array {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw ?: '[]', true);
    return is_array($data) ? $data : [];
}

function sx_uuid(): string {
    return bin2hex(random_bytes(16));
}

function sx_json(array $data, int $code = 200): void {
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

function sx_find_user_by_email(array $users, string $email): ?array {
    $email = mb_strtolower(trim($email));
    foreach ($users as $u) {
        if (isset($u['email']) && mb_strtolower($u['email']) === $email) return $u;
    }
    return null;
}

function sx_find_user_index(array $users, string $id): int {
    foreach ($users as $i => $u) {
        if (($u['id'] ?? null) === $id) return $i;
    }
    return -1;
}

function sx_current_user(): ?array {
    sx_session_start();
    $uid = $_SESSION['uid'] ?? null;
    if (!$uid) return null;
    $users = sx_read_users();
    foreach ($users as $u) if (($u['id'] ?? null) === $uid) return $u;
    return null;
}

function sx_require_auth(): array {
    $u = sx_current_user();
    if (!$u) sx_json(['error' => 'Требуется вход.'], 401);
    return $u;
}

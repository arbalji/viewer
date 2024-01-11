<?php
// Set the appropriate headers to allow cross-origin requests
header("Access-Control-Allow-Origin: *");
header("Access-Control-Allow-Methods: GET, POST, OPTIONS");
header("Access-Control-Allow-Headers: *");
header("Content-type: image/jpeg");

// Get the image URL from the query string
$imageUrl = isset($_GET['url']) ? $_GET['url'] : null;

// Validate the URL (you might want to add more validation)
if (!$imageUrl || !filter_var($imageUrl, FILTER_VALIDATE_URL)) {
    header("HTTP/1.1 400 Bad Request");
    echo "Invalid or missing image URL";
    exit;
}

// Fetch the image content
$imageContent = @file_get_contents($imageUrl);

// Check if fetching the image content was successful
if ($imageContent === false) {
    header("HTTP/1.1 500 Internal Server Error");
    echo "Error fetching image content";
    exit;
}

// Output the image content
echo $imageContent;

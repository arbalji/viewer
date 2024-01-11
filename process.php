<?php
// Set the appropriate headers to allow cross-origin requests
header("Access-Control-Allow-Origin: *");
header("Access-Control-Allow-Methods: GET, POST, OPTIONS");
header("Access-Control-Allow-Headers: *");
header("Content-type: image/jpeg");

// Get the image URL from the query string
$imageUrl = $_GET['url'];

// Fetch the image content and output it
echo file_get_contents($imageUrl);

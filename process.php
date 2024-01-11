<?php
// Set the appropriate headers to allow cross-origin requests
header("Access-Control-Allow-Origin: *");
header("Access-Control-Allow-Methods: GET, POST, OPTIONS");
header("Access-Control-Allow-Headers: *");
header("Content-type: application/json");

// Check if the request contains the necessary data
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $image = $_POST['image'] ?? '';
    $iframe = $_POST['iframe'] ?? '';

    if (!empty($image) && !empty($iframe)) {
        // Perform actions with the received data
        // For example: Process the image and iframe data to generate a new URL

        // Generate a new URL based on the received data
        $newURL = "http://localhost/your_new_url.php?url=" . urlencode($image) . "&iframe=" . urlencode($iframe);

        // Log the received data and generated URL
        $log = "Received Image URL: " . $image . "\n";
        $log .= "Received Iframe URL: " . $iframe . "\n";
        $log .= "Generated New URL: " . $newURL . "\n";

        // Save the log to a file (you can adjust the file path and name)
        file_put_contents('received_data.log', $log, FILE_APPEND | LOCK_EX);

        // Send the generated URL as a response
        $response = json_encode(array('status' => 'success', 'new_url' => $newURL));
        echo $response;
    } else {
        // If the required data is missing
        $response = json_encode(array('status' => 'error', 'message' => 'Missing required data.'));
        echo $response;
    }
} else {
    // If the request method is not POST
    $response = json_encode(array('status' => 'error', 'message' => 'Invalid request method.'));
    echo $response;
}
?>

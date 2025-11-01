// k6 load testing script for WordPress
import http from 'k6/http';
import { check, sleep } from 'k6';

// Configuration for load tests
export const options = {
    stages: [
        { duration: '5m', target: 50 }, // Ramp-up to 50 users
        { duration: '10m', target: 50 }, // Stay at 50 users
        { duration: '5m', target: 0 }, // Ramp-down to 0 users
    ],
};

// Basic Load Test: Simulates users accessing the WordPress homepage
export default function () {
    // Basic Load Test
    let res = http.get('http://10.187.36.245:30080/');
    check(res, {
        'homepage status is 200': (r) => r.status === 200,
    });

    // API Load Test: Tests the performance of the WordPress REST API
    res = http.get('http://10.187.36.245:30080/wp-json/wp/v2/posts');
    check(res, {
        'API status is 200': (r) => r.status === 200,
    });

    // Database Load Test: Simulates interactions that involve database queries
    res = http.get('http://10.187.36.245:30080/wp-json/wp/v2/comments');
    check(res, {
        'Comments API status is 200': (r) => r.status === 200,
    });

    sleep(1); // Wait for 1 second before the next iteration
}
#!/usr/bin/env python3
"""Test script to verify worker caching optimization."""

import multiprocessing
import time
from repomap.repo_tree import RepoTreeGenerator

def test_worker_function(dummy_data):
    """Test that worker function properly caches processor instance."""
    file_info = (
        'test.c',  # path
        {'type': 'blob'},  # item
        'https://example.com/repo',  # repo_url
        'main',  # ref
        None,  # token
        False,  # use_local_clone
        None  # local_clone_path
    )
    
    start_time = time.time()
    result = RepoTreeGenerator._process_file_worker(file_info)
    elapsed = time.time() - start_time
    
    return elapsed, hasattr(RepoTreeGenerator._process_file_worker, '_processor')

if __name__ == '__main__':
    print("Testing worker processor caching...")
    
    # Test with multiprocessing
    with multiprocessing.Pool(processes=2) as pool:
        results = pool.map(test_worker_function, [1, 2, 3, 4])
    
    print("Worker execution times and cache status:")
    for i, (elapsed, has_cache) in enumerate(results):
        print(f"  Task {i+1}: {elapsed:.3f}s, cached: {has_cache}")
        
    print("If caching works, subsequent tasks should be faster!")
"""
Profile ID Utilities - SINGLE SOURCE OF TRUTH for LinkedIn profile identification.
Copied from apify-api/api-backend/services/profile_id_utils.py

LinkedIn has TWO types of identifiers:
1. **Username/publicId**: Human-readable, e.g., 'zainjaffer' - CAN CHANGE
2. **URN/profileId**: Permanent unique ID, e.g., 'ACoAAAEZSvUBnQ2RoBurjWCQRGhx-Rq8P6L7uEk' - NEVER CHANGES

DECISION: We use the URN-style profileId as the canonical identifier everywhere because:
- It's permanent (usernames can change)
- It's what LinkedIn uses internally
- It ensures consistency across all tables

This module provides helper functions that ALL code should use to extract profile IDs.
"""

from typing import Dict, Optional


def get_profile_id_from_post(post: Dict) -> Optional[str]:
    """
    Extract the canonical profile ID from a post object (from Posts Scraper).
    
    Priority order (URN-style first, fallback to username):
    1. author.profileId (URN-style, preferred)
    2. authorProfileId (username-style, fallback)
    3. author.publicId (username-style, fallback)
    
    Args:
        post: Raw post object from Apify Posts Scraper
    
    Returns:
        Profile ID string or None if not found
    """
    author_obj = post.get('author', {})
    
    if isinstance(author_obj, dict):
        # Preferred: URN-style profileId
        profile_id = author_obj.get('profileId')
        if profile_id:
            return profile_id
    
    # Fallback 1: authorProfileId (usually username-style)
    profile_id = post.get('authorProfileId')
    if profile_id:
        return profile_id
    
    # Fallback 2: author.publicId
    if isinstance(author_obj, dict):
        profile_id = author_obj.get('publicId')
        if profile_id:
            return profile_id
    
    return None


def get_profile_id_from_profile(profile: Dict) -> Optional[str]:
    """
    Extract the canonical profile ID from a profile object (from Profile Scraper).
    
    Priority order (URN-style first):
    1. profileId (URN-style, preferred)
    2. id (sometimes contains URN)
    3. publicIdentifier (username-style, fallback)
    
    Args:
        profile: Raw profile object from Apify Profile Scraper
    
    Returns:
        Profile ID string or None if not found
    """
    # Preferred: URN-style profileId
    profile_id = profile.get('profileId')
    if profile_id:
        return profile_id
    
    # Sometimes the 'id' field contains the URN
    profile_id = profile.get('id')
    if profile_id and profile_id.startswith('ACoAAA'):
        return profile_id
    
    # Fallback: publicIdentifier (username-style)
    profile_id = profile.get('publicIdentifier')
    if profile_id:
        return profile_id
    
    return None


def get_resharer_id(reshared_post: Dict) -> Optional[str]:
    """
    Get the profile ID of the person who reshared a post.
    
    Args:
        reshared_post: Post object that is a reshare
    
    Returns:
        Profile ID of the resharer or None
    """
    if 'resharedPost' in reshared_post:
        author_obj = reshared_post.get('author', {})
        if isinstance(author_obj, dict):
            # Prefer URN-style
            author_id = author_obj.get('profileId')
            if author_id:
                return author_id
        # Fallback to authorProfileId
        author_id = reshared_post.get('authorProfileId')
        if author_id:
            return author_id
            
    elif reshared_post.get('isActivity') is True:
        activity_user = reshared_post.get('activityOfUser', {})
        if isinstance(activity_user, dict):
            author_id = activity_user.get('profileId')
            if author_id:
                return author_id
    
    return None


def is_urn_style_id(profile_id: str) -> bool:
    """
    Check if a profile ID is URN-style (permanent) or username-style.
    
    URN-style IDs start with 'ACoAAA' and are ~43 characters long.
    Username-style IDs are shorter, human-readable strings.
    
    Args:
        profile_id: The profile ID to check
    
    Returns:
        True if URN-style, False if username-style
    """
    if not profile_id:
        return False
    return profile_id.startswith('ACoAAA') and len(profile_id) > 30


def get_public_identifier(profile: Dict) -> Optional[str]:
    """
    Get the public username/identifier from a profile (for URL building).
    
    This is the human-readable username like 'zainjaffer'.
    Use this for building LinkedIn URLs, NOT for database keys.
    
    Args:
        profile: Raw profile object from Apify
    
    Returns:
        Public identifier string or None
    """
    return (
        profile.get('publicIdentifier') or
        profile.get('publicId') or
        profile.get('author', {}).get('publicId')
    )

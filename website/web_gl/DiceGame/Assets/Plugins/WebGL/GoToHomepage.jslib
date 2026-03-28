mergeInto(LibraryManager.library, {
    GoToHomepage: function() {
        // Site root (main page). top = exit iframes; replace = avoid stacking game URL in history.
        var home = window.location.origin + '/';
        try {
            window.top.location.replace(home);
        } catch (e) {
            window.location.replace(home);
        }
    }
});

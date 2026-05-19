from mudclient.profiles import Profile, ProfileStore


def test_profile_create_delete(tmp_path):
    store = ProfileStore(config_dir=tmp_path)
    p = Profile(name="main", host="example.com", port=4000)
    store.save_profile(p)
    assert store.get("main") is not None
    assert len(store.list_profiles()) == 1
    assert store.delete_profile("main") is True
    assert store.get("main") is None

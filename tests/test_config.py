from mudclient.config import ClientConfig, ConfigStore, HighlightRule, TriggerRule


def test_config_save_load(tmp_path):
    store = ConfigStore(config_dir=tmp_path)
    cfg = ClientConfig(
        encoding="latin-1",
        log_raw_ansi=True,
        highlights=[HighlightRule(pattern="dragon", style="ansired")],
        triggers=[TriggerRule(pattern="HP low", response="heal", enabled=True)],
    )
    store.save(cfg)
    loaded = store.load()
    assert loaded.encoding == "latin-1"
    assert loaded.log_raw_ansi is True
    assert loaded.highlights[0].pattern == "dragon"
    assert loaded.triggers[0].response == "heal"

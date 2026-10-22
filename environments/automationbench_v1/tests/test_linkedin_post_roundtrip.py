"""LinkedIn API aliases must survive the environment's persisted world format."""

import json

import pytest
from pydantic import ValidationError

from automationbench.domains.sales.tasks import get_sales_milestone_task
from automationbench.schema.linkedin.post import Post, PostContent
from automationbench.schema.world import WorldState
from automationbench_v1.scoring import score_world
from automationbench_v1.world_codec import dump_world, load_world


@pytest.mark.parametrize("article", [None, "https://example.com/milestone"])
def test_linkedin_post_survives_persisted_world_reload(article):
    content = PostContent(
        articleUrl=article, articleTitle="Milestone", articleDescription="Reached target"
    )
    world = WorldState()
    world.linkedin.posts.append(Post(text="Milestone reached", content=content))
    restored = load_world(json.loads(json.dumps(dump_world(world))))
    post = restored.linkedin.posts[0]
    assert isinstance(post.content, PostContent)
    assert post.content.article_url == article
    assert post.content.article_title == "Milestone"
    assert post.content.article_description == "Reached target"
    assert dump_world(restored) == dump_world(world)


def test_article_aliases_and_field_names_both_remain_valid():
    alias = PostContent(articleUrl="https://example.com", articleTitle="Title")
    assert PostContent.model_validate(alias.model_dump()) == alias
    with pytest.raises(ValidationError, match="extra_forbidden"):
        PostContent.model_validate({"article_typo": "not a valid field"})


def test_milestone_scoring_accepts_persisted_linkedin_post():
    info = get_sales_milestone_task()["info"]
    world = WorldState.model_validate(info["initial_state"])
    world.linkedin.posts.append(
        Post(text="ARR 5247000 #ARRMilestone", content=PostContent(articleTitle="ARR"))
    )
    snapshot = score_world(
        world=json.loads(json.dumps(dump_world(world))),
        initial_state=info["initial_state"],
        assertions=tuple(info["assertions"]),
    )
    assert snapshot.assertions_scored > 0
    assert any(
        result["passed"]
        for result in snapshot.assertion_results
        if result["type"].startswith("linkedin_")
    )
    assert snapshot.end_state["linkedin"]["posts"][0]["content"]["article_title"] == "ARR"

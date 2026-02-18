from typing import List, Dict, Any, Optional
from collections import defaultdict
import numpy as np
import logging

logger = logging.getLogger(__name__)


class RLRecommendationService:

    def __init__(self, epsilon: float = 0.1, learning_rate: float = 0.01):
        self.epsilon = epsilon
        self.learning_rate = learning_rate
        self.user_topic_weights: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self.article_scores: Dict[str, float] = defaultdict(lambda: 0.5)
        self.user_article_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        logger.info("RL Recommendation Service initialized")

    def is_available(self) -> bool:
        return True

    async def get_recommendations(
        self,
        user_id: str,
        candidate_articles: List[Dict[str, Any]],
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        try:
            recommendations = []

            for article in candidate_articles:
                article_id = str(article.get('article_id', article.get('id', '')))
                topics = article.get('topics', [])

                score = await self._calculate_score(user_id, article_id, topics)
                recommendations.append({
                    'article_id': article_id,
                    'score': score,
                    'article': article
                })

            if np.random.random() < self.epsilon:
                np.random.shuffle(recommendations)
            else:
                recommendations.sort(key=lambda x: x['score'], reverse=True)

            return recommendations[:top_k]

        except Exception as e:
            logger.error(f"Error in get_recommendations: {e}")
            np.random.shuffle(candidate_articles)
            return [
                {
                    'article_id': str(a.get('article_id', a.get('id', ''))),
                    'score': 0.5,
                    'article': a
                }
                for a in candidate_articles[:top_k]
            ]

    async def _calculate_score(
        self,
        user_id: str,
        article_id: str,
        topics: List[str]
    ) -> float:
        score = self.article_scores[article_id]

        if topics:
            topic_scores = [
                self.user_topic_weights[user_id].get(topic, 0.0)
                for topic in topics
            ]
            topic_score = np.mean(topic_scores) if topic_scores else 0.0
            score = (score * 0.6) + (topic_score * 0.4)

        interaction_count = self.user_article_counts[user_id][article_id]
        total_interactions = max(sum(self.user_article_counts[user_id].values()), 1)
        exploration_bonus = np.sqrt(2 * np.log(total_interactions) / max(interaction_count, 1))
        score += exploration_bonus * 0.1

        return float(np.clip(score, 0.0, 1.0))

    async def update_from_feedback(
        self,
        user_id: str,
        article_id: str,
        topics: List[str],
        feedback: str,
        engagement_metrics: Optional[Dict[str, Any]] = None
    ):
        try:
            reward_map = {
                'positive': 1.0,
                'neutral': 0.5,
                'negative': 0.0
            }
            reward = reward_map.get(feedback, 0.5)

            if engagement_metrics:
                time_spent = engagement_metrics.get('time_spent_seconds', 0)
                if time_spent > 60:
                    reward = min(reward + 0.2, 1.0)

            current_score = self.article_scores[article_id]
            self.article_scores[article_id] = current_score + self.learning_rate * (reward - current_score)

            for topic in topics:
                current_weight = self.user_topic_weights[user_id][topic]
                self.user_topic_weights[user_id][topic] = current_weight + self.learning_rate * (reward - current_weight)

            self.user_article_counts[user_id][article_id] += 1

            logger.info(f"Updated RL model: user={user_id}, article={article_id}, reward={reward}")

        except Exception as e:
            logger.error(f"Error updating RL model: {e}")

    async def get_user_preferences(self, user_id: str) -> Dict[str, float]:
        return dict(self.user_topic_weights[user_id])

    async def reset_user_preferences(self, user_id: str):
        if user_id in self.user_topic_weights:
            del self.user_topic_weights[user_id]
        if user_id in self.user_article_counts:
            del self.user_article_counts[user_id]
        logger.info(f"Reset preferences for user {user_id}")


rl_service = RLRecommendationService()

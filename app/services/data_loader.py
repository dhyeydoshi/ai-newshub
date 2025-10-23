"""
Data Loading Service for RL Training
Bridges database models with RL training pipeline
"""
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone, timedelta
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import joinedload

from app.models.user import User
from app.models.article import Article
from app.models.feedback import ReadingHistory, UserFeedback

logger = logging.getLogger(__name__)


class RLDataLoader:
    """Load and prepare data from database for RL training"""

    @staticmethod
    async def load_user_training_data(
        db: AsyncSession,
        user_ids: Optional[List[int]] = None,
        min_interactions: int = 5,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Load user data with reading history and feedback for training

        Args:
            db: Database session
            user_ids: Specific user IDs to load (None = all active users)
            min_interactions: Minimum interactions required
            limit: Maximum number of users to load

        Returns:
            List of user data dictionaries
        """
        query = select(User).options(
            joinedload(User.reading_history),
            joinedload(User.feedback)
        ).where(User.is_active == True)

        if user_ids:
            query = query.where(User.id.in_(user_ids))

        # Filter users with minimum interactions
        query = query.join(ReadingHistory).group_by(User.id).having(
            func.count(ReadingHistory.id) >= min_interactions
        ).limit(limit)

        result = await db.execute(query)
        users = result.scalars().unique().all()

        user_data_list = []
        for user in users:
            # Get reading history
            reading_history = []
            for history in user.reading_history[-100:]:  # Last 100 interactions
                if history.article:
                    reading_history.append({
                        'article_id': history.article.article_id,
                        'topics': history.article.topics or [],
                        'time_spent_seconds': history.time_spent_seconds or 0.0,
                        'clicked': history.clicked,
                        'timestamp': history.viewed_at
                    })

            # Get feedback history
            feedback_history = []
            for feedback in user.feedback:
                if feedback.article:
                    feedback_history.append({
                        'feedback_type': feedback.feedback_type,
                        'article_topics': feedback.article.topics or [],
                        'rating': feedback.rating,
                        'timestamp': feedback.created_at
                    })

            user_data = {
                'user_id': str(user.id),
                'reading_history': reading_history,
                'feedback_history': feedback_history
            }

            user_data_list.append(user_data)

        logger.info(f"Loaded {len(user_data_list)} users for training")
        return user_data_list

    @staticmethod
    async def load_articles_data(
        db: AsyncSession,
        days_back: int = 30,
        limit: int = 1000,
        min_word_count: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Load articles for training

        Args:
            db: Database session
            days_back: Load articles from last N days
            limit: Maximum number of articles
            min_word_count: Minimum word count

        Returns:
            List of article dictionaries
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)

        query = select(Article).where(
            and_(
                Article.is_active == True,
                Article.published_at >= cutoff_date,
                Article.word_count >= min_word_count
            )
        ).order_by(Article.published_at.desc()).limit(limit)

        result = await db.execute(query)
        articles = result.scalars().all()

        articles_data = [article.to_dict() for article in articles]

        logger.info(f"Loaded {len(articles_data)} articles for training")
        return articles_data

    @staticmethod
    async def split_users_train_eval(
        user_data_list: List[Dict[str, Any]],
        eval_ratio: float = 0.2
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Split users into training and evaluation sets

        Args:
            user_data_list: List of user data
            eval_ratio: Ratio for evaluation set

        Returns:
            Tuple of (train_users, eval_users)
        """
        import random
        random.shuffle(user_data_list)

        split_idx = int(len(user_data_list) * (1 - eval_ratio))
        train_users = user_data_list[:split_idx]
        eval_users = user_data_list[split_idx:]

        logger.info(f"Split: {len(train_users)} train, {len(eval_users)} eval users")
        return train_users, eval_users

    @staticmethod
    async def load_training_batch(
        db: AsyncSession,
        batch_size: int = 100,
        days_back: int = 30
    ) -> Dict[str, Any]:
        """
        Load a complete training batch (users + articles)

        Args:
            db: Database session
            batch_size: Number of users to load
            days_back: Days of articles to load

        Returns:
            Dictionary with train_users, eval_users, articles
        """
        # Load users
        user_data_list = await RLDataLoader.load_user_training_data(
            db=db,
            limit=batch_size
        )

        # Load articles
        articles_data = await RLDataLoader.load_articles_data(
            db=db,
            days_back=days_back
        )

        # Split users
        train_users, eval_users = await RLDataLoader.split_users_train_eval(
            user_data_list
        )

        return {
            'train_users': train_users,
            'eval_users': eval_users,
            'articles': articles_data
        }


class DataExporter:
    """Export database data to JSON files for offline training"""

    @staticmethod
    async def export_training_data(
        db: AsyncSession,
        output_dir: str,
        batch_size: int = 1000,
        days_back: int = 30
    ):
        """
        Export training data to JSON files

        Args:
            db: Database session
            output_dir: Output directory path
            batch_size: Number of users per batch
            days_back: Days of articles to export
        """
        import json
        from pathlib import Path

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Load data
        data = await RLDataLoader.load_training_batch(
            db=db,
            batch_size=batch_size,
            days_back=days_back
        )

        # Convert datetime objects to ISO strings
        def serialize_datetime(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")

        # Export train users
        with open(output_path / 'train_users.json', 'w') as f:
            json.dump(data['train_users'], f, default=serialize_datetime, indent=2)

        # Export eval users
        with open(output_path / 'eval_users.json', 'w') as f:
            json.dump(data['eval_users'], f, default=serialize_datetime, indent=2)

        # Export articles
        with open(output_path / 'articles.json', 'w') as f:
            json.dump(data['articles'], f, default=serialize_datetime, indent=2)

        logger.info(f"Exported training data to {output_dir}")
        logger.info(f"Train users: {len(data['train_users'])}")
        logger.info(f"Eval users: {len(data['eval_users'])}")
        logger.info(f"Articles: {len(data['articles'])}")


# Synchronous wrapper for use in training scripts
class SyncRLDataLoader:
    """Synchronous data loader for training scripts"""

    @staticmethod
    def load_from_json(data_dir: str) -> Dict[str, Any]:
        """
        Load data from exported JSON files

        Args:
            data_dir: Directory with JSON files

        Returns:
            Dictionary with train_users, eval_users, articles
        """
        import json
        from pathlib import Path
        from datetime import datetime

        data_path = Path(data_dir)

        def parse_datetime(obj):
            """Recursively parse ISO datetime strings"""
            if isinstance(obj, dict):
                return {k: parse_datetime(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [parse_datetime(item) for item in obj]
            elif isinstance(obj, str):
                try:
                    # Try to parse as datetime
                    return datetime.fromisoformat(obj.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    return obj
            return obj

        # Load files
        with open(data_path / 'train_users.json', 'r') as f:
            train_users = json.load(f)
            train_users = parse_datetime(train_users)

        with open(data_path / 'eval_users.json', 'r') as f:
            eval_users = json.load(f)
            eval_users = parse_datetime(eval_users)

        with open(data_path / 'articles.json', 'r') as f:
            articles = json.load(f)
            articles = parse_datetime(articles)

        logger.info(f"Loaded data from {data_dir}")
        logger.info(f"Train users: {len(train_users)}")
        logger.info(f"Eval users: {len(eval_users)}")
        logger.info(f"Articles: {len(articles)}")

        return {
            'train_users': train_users,
            'eval_users': eval_users,
            'articles': articles
        }


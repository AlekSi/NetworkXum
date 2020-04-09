from abc import ABC, abstractmethod

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, Text, Float, Boolean
from sqlalchemy.sql import func
from sqlalchemy import or_, and_
from sqlalchemy_utils import create_database, database_exists
from sqlalchemy import text

from pygraphdb.graph_base import GraphBase
from pygraphdb.edge import Edge
from pygraphdb.helpers import *

BaseEntitySQL = declarative_base()


class NodeSQL(BaseEntitySQL):
    __tablename__ = 'table_nodes'
    _id = Column(BigInteger, primary_key=True)
    attributes_json = Column(Text)

    def __init__(self, *args, **kwargs):
        BaseEntitySQL.__init__(self)


class EdgeSQL(BaseEntitySQL, Edge):
    __tablename__ = 'table_edges'
    _id = Column(BigInteger, primary_key=True)
    v_from = Column(BigInteger, index=True)
    v_to = Column(BigInteger, index=True)
    weight = Column(Float)
    attributes_json = Column(Text)

    def __init__(self, *args, **kwargs):
        BaseEntitySQL.__init__(self)
        Edge.__init__(self, *args, **kwargs)


class EdgeNew(BaseEntitySQL, Edge):
    __tablename__ = 'new_edges'
    _id = Column(BigInteger, primary_key=True)
    v_from = Column(BigInteger, index=False)
    v_to = Column(BigInteger, index=False)
    weight = Column(Float)
    attributes_json = Column(Text)

    def __init__(self, *args, **kwargs):
        BaseEntitySQL.__init__(self)
        Edge.__init__(self, *args, **kwargs)


class PlainSQL(GraphBase):
    """
        A generic SQL-compatiable wrapper for Graph-shaped data.
        It's built on top of SQLAlchemy which supports following engines: 
        *   SQLite, 
        *   PostgreSQL, 
        *   MySQL, 
        *   Oracle, 
        *   MS-SQL, 
        *   Firebird, 
        *   Sybase. 
        Other dialects are published as external projects.
        This wrapper does not only emit the query results, 
        but can export the serialized quaery itself to be used 
        with other SQL-compatible systems.
        Docs: https://docs.python.org/3/library/sqlite3.html

        CAUTION:
        Implementations of analytical queries are suboptimal, 
        as implementing them in SQL dialects is troublesome and 
        often results in excessive memory consumption, 
        when temporary tables are created.

        CAUTION:
        Queries can be exported without execution with `str(query)`, 
        but if you want to compile them for a specific dialect use following snippet:
        >>> str(query.statement.compile(dialect=postgresql.dialect()))
        Source: http://nicolascadou.com/blog/2014/01/printing-actual-sqlalchemy-queries/
    """
    __max_batch_size__ = 5000

    def __init__(self, url='sqlite:///:memory:'):
        super().__init__()
        # https://stackoverflow.com/a/51184173
        if not database_exists(url):
            create_database(url)
        self.engine = sa.create_engine(url)
        self.session_maker = sessionmaker(bind=self.engine)
        self.session = self.session_maker()
        BaseEntitySQL.metadata.create_all(self.engine)

    # Relatives

    def find_edge(self, v_from: int, v_to: int) -> Optional[EdgeSQL]:
        return self.session.query(EdgeSQL).filter(and_(
            EdgeSQL.v_from == v_from,
            EdgeSQL.v_to == v_to,
        )).first()

    def find_edge_or_inv(self, v1: int, v2: int) -> Optional[EdgeSQL]:
        return self.session.query(EdgeSQL).filter(or_(
            and_(
                EdgeSQL.v_from == v1,
                EdgeSQL.v_to == v2,
            ),
            and_(
                EdgeSQL.v_from == v2,
                EdgeSQL.v_to == v1,
            )
        )).all()

    def edges_from(self, v: int) -> List[EdgeSQL]:
        return self.session.query(EdgeSQL).filter_by(v_from=v).all()

    def edges_to(self, v: int) -> List[EdgeSQL]:
        return self.session.query(EdgeSQL).filter_by(v_to=v).all()

    def edges_related(self, v: int) -> List[EdgeSQL]:
        return self.session.query(EdgeSQL).filter(or_(
            EdgeSQL.v_from == v,
            EdgeSQL.v_to == v,
        )).all()

    def all_vertexes(self) -> Set[int]:
        all_froms = self.session.query(EdgeSQL.v_from).distinct().all()
        all_tos = self.session.query(EdgeSQL.v_to).distinct().all()
        return set(all_froms).union(all_tos)

    # Wider range of neighbors

    def nodes_related_to_group(self, vs: Sequence[int]) -> Set[int]:
        edges = self.session.query(EdgeSQL).filter(or_(
            EdgeSQL.v_from.in_(vs),
            EdgeSQL.v_to.in_(vs),
        )).all()
        result = set()
        for e in edges:
            if (e.v_from not in vs):
                result.add(e.v_from)
            elif (e.v_to not in vs):
                result.add(e.v_to)
        return result

    # Metadata

    def count_nodes(self) -> int:
        return len(self.all_vertexes())

    def count_edges(self) -> int:
        return self.session.query(EdgeSQL).count()

    def count_related(self, v: int) -> (int, float):
        return self.session.query(
            func.count(EdgeSQL.weight).label("count"),
            func.sum(EdgeSQL.weight).label("sum"),
        ).filter(or_(
            EdgeSQL.v_from == v,
            EdgeSQL.v_to == v,
        )).first()

    def count_followers(self, v: int) -> (int, float):
        return self.session.query(
            func.count(EdgeSQL.weight).label("count"),
            func.sum(EdgeSQL.weight).label("sum"),
        ).filter_by(v_to=v).first()

    def count_following(self, v: int) -> (int, float):
        return self.session.query(
            func.count(EdgeSQL.weight).label("count"),
            func.sum(EdgeSQL.weight).label("sum"),
        ).filter_by(v_from=v).first()

    # Modifications

    def insert_edge(self, e: EdgeSQL) -> bool:
        e = self._to_sql(e, e_type=EdgeSQL)
        self.session.merge(e)
        self.session.commit()

    def remove_edge(self, e: EdgeSQL) -> bool:
        if '_id' in e:
            self.session.query(EdgeSQL).filter_by(
                _id=e['_id']
            ).delete()
        else:
            self.session.query(EdgeSQL).filter_by(
                v_from=e['v_from'],
                v_to=e['v_to'],
            ).delete()
        self.session.commit()

    def insert_edges(self, es: List[Edge]) -> int:
        for e in es:
            e = self._to_sql(e, e_type=EdgeSQL)
            self.session.merge(e)
        try:
            self.session.commit()
            return len(es)
        except:
            return 0

    def remove_node(self, v: int) -> int:
        try:
            count = self.session.query(EdgeSQL).filter(or_(
                EdgeSQL.v_from == v,
                EdgeSQL.v_to == v,
            )).delete()
            self.session.commit()
            return count
        except:
            self.session.rollback()
            return 0

    def remove_all(self) -> int:
        try:
            count = 0
            count += self.session.query(EdgeSQL).delete()
            count += self.session.query(EdgeNew).delete()
            self.session.commit()
            return count
        except:
            self.session.rollback()

    def insert_dump(self, path: str) -> int:
        """
            Direct injections (even in batches) have huge performance impact.
            We are not only conflicting with other operations in same DB, 
            but also constantly rewriting indexes after every new batch insert.
            Instead we create a an additional unindexed table, fill it and
            then merge into the main one.
        """
        try:
            cnt = self.count_edges()
            # Build the new table.
            chunk_len = PlainSQL.__max_batch_size__
            for es in chunks(yield_edges_from(path), chunk_len):
                es = [self._to_sql(e) for e in es]
                self.insert_edges(es)
            self.session.commit()
            # Import the new data.
            self.insert_table(EdgeNew.__tablename__)
            self.flush_temporary_table()
            return self.count_edges() - cnt
        except Exception as e:
            print(e)
            self.session.rollback()
            return 0

    @abstractmethod
    def insert_table(self, source_name: str):
        migration = text(f'''
            REPLACE INTO {EdgeSQL.__tablename__}
            SELECT * FROM {source_name};
        ''')
        # Performing an `INSERT` and then a `DELETE` might lead to integrity issues,
        # so perhaps a way to get around it, and to perform everything neatly in
        # a single statement, is to take advantage of the `[deleted]` temporary table.
        # migration = text(f'''
        # DELETE {EdgeNew.__tablename__};
        # OUTPUT DELETED.*
        # INTO {EdgeSQL.__tablename__} (_id, v_from, v_to, weight, attributes_json)
        # ''')
        # But this syntax isn't globally supported.
        self.session.execute(step)
        self.session.commit()

    def insert_bulk_deduplicated(self, es: List[EdgeNew]):
        # Some low quality datasets contain duplicates and
        # if we have ID collisions, the operation will fail.
        # https://docs.sqlalchemy.org/en/13/orm/session_api.html#sqlalchemy.orm.session.Session.bulk_save_objects
        self.session.bulk_save_objects(
            es_filtered,
            return_defaults=False,
            update_changed_only=True,
            preserve_order=False,
        )
        self.session.commit()

    def flush_temporary_table(self):
        self.session.execute(text(f'DELETE FROM {EdgeNew.__tablename__};'))
        self.session.commit()

    def _to_sql(self, e, e_type=EdgeSQL) -> BaseEntitySQL:
        if isinstance(e, BaseEntitySQL):
            return e
        return e_type(e['v_from'], e['v_to'], e['weight'])

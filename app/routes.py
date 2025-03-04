import markdown
from flask import Blueprint, render_template, request, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func
from sqlmodel import Session, select, desc
from werkzeug.utils import redirect
from datetime import datetime

from app import engine, app, mail
from app.md_processor import CustomMarkdownExtension
from app.models import Post, User, Comment, Like
from app.forms import CommentForm, EditCommentForm, PostForm

# 创建蓝图
main = Blueprint('main', __name__)


@main.route('/')
def index():
    with Session(engine) as session:
        # 查询最新的 10 篇博文，按创建时间倒序排列
        posts = session.exec(
            select(Post)
            .order_by(desc(Post.created_at))
            .limit(10)
        ).all()

        popular_posts = session.exec(
            select(Post)
            .order_by(desc(func.count(Like.id)))
            .join(Like, isouter=True)
            .group_by(Post.id)
            .limit(5)
        ).all()

        return render_template('index.html', posts=posts, datetime=datetime, len=len, popular_posts=popular_posts)


@main.route('/dashboard')
@login_required
def dashboard():
    with Session(engine) as session:
        user = session.exec(
            select(User).where(User.id == current_user.id)
        ).first()
        if user:

            # 显式加载 posts 关系
            session.refresh(user)
            posts = user.posts if hasattr(user, "posts") else []
        else:
            posts = []
        return render_template('dashboard.html', name=current_user.username, posts=posts)


@main.route('/create_post', methods=['GET', 'POST'])
@login_required
def create_post():
    form = PostForm()
    if form.validate_on_submit():
        html_content = markdown.Markdown(
            extensions=[CustomMarkdownExtension()]
        ).convert(form.content.data)  # 解析 Markdown
        new_post = Post(
            title=form.title.data,
            content=form.content.data,
            html_content=html_content,
            author_id=current_user.id
        )
        with Session(engine) as session:
            session.add(new_post)
            session.commit()
            flash('博文已发布！', 'success')
            return redirect(url_for('main.dashboard'))
    return render_template('create_post.html', form=form)


@main.route('/post/<int:post_id>')
def view_post(post_id):
    with Session(engine) as session:
        post = session.get(Post, post_id)
        if post:
            return render_template('view_post.html', post=post, form=CommentForm())
        else:
            flash('博文未找到！')
            return redirect(url_for('main.index'))


@main.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment(post_id):
    form = CommentForm()
    if form.validate_on_submit():
        html_content = markdown.Markdown(
            extensions=[CustomMarkdownExtension()]
        ).convert(form.content.data)  # 解析 Markdown
        new_comment = Comment(
            content=form.content.data,
            html_content=html_content,
            author_id=current_user.id,
            post_id=post_id
        )
        with Session(engine) as session:
            session.add(new_comment)
            session.commit()
            flash('评论已发布！', 'success')
    return redirect(url_for('main.view_post', post_id=post_id))


@main.route('/edit_post/<int:post_id>', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    with Session(engine) as session:
        post = session.get(Post, post_id)
        if not post:
            flash('博文未找到!')
            return redirect(url_for('main.dashboard'))
        if post.author_id != current_user.id and not current_user.is_admin:
            flash('你没有编辑这篇博文的权限!')
            return redirect(url_for('main.dashboard'))

        if request.method == 'POST':
            title = request.form.get('title')
            content = request.form.get('content')

            if not title or not content:
                flash('你必须填写标题和内容字段!')
            else:
                post.title = title
                post.content = content
                post.html_content = markdown.Markdown(
                    extensions=[CustomMarkdownExtension()]
                ).convert(content)  # 转换 Markdown
                session.commit()
                flash('你的博文已被更新!')
                return redirect(url_for('main.view_post', post_id=post.id))

        return render_template('edit_post.html', post=post, form=CommentForm())


@main.route('/delete_post/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    with Session(engine) as session:
        post = session.get(Post, post_id)
        if not post:
            flash('博文未找到!')
            return redirect(url_for('main.dashboard'))
        if post.author_id != current_user.id and not current_user.is_admin:
            flash('你没有删除这篇博文的权限!')
            return redirect(url_for('main.dashboard'))

        session.delete(post)
        session.commit()
        flash('你的博文已被删除!')
        return redirect(url_for('main.dashboard'))


@main.route('/comment/<int:comment_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_comment(comment_id):
    with Session(engine) as session:
        comment = session.get(Comment, comment_id)
        if not comment:
            flash('评论未找到！', 'error')
            return redirect(url_for('main.index'))
        if comment.author_id != current_user.id and not current_user.is_admin:
            flash('你没有权限编辑这条评论！', 'error')
            return redirect(url_for('main.view_post', post_id=comment.post_id))

        form = EditCommentForm()
        if form.validate_on_submit():
            comment.content = form.content.data
            comment.html_content = markdown.Markdown(
                extensions=[CustomMarkdownExtension()]
            ).convert(form.content.data)  # 解析 Markdown
            session.commit()
            flash('评论已更新！', 'success')
            return redirect(url_for('main.view_post', post_id=comment.post_id))
        elif request.method == 'GET':
            form.content.data = comment.content

        return render_template('edit_comment.html', form=form, comment=comment)


# 删除评论
@main.route('/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_comment(comment_id):
    with Session(engine) as session:
        comment = session.get(Comment, comment_id)
        if not comment:
            flash('评论未找到！', 'error')
            return redirect(url_for('main.index'))
        if comment.author_id != current_user.id and not current_user.is_admin:
            flash('你没有权限删除这条评论！', 'error')
            return redirect(url_for('main.view_post', post_id=comment.post_id))

        post_id = comment.post_id
        session.delete(comment)
        session.commit()
        flash('评论已删除！', 'success')
        return redirect(url_for('main.view_post', post_id=post_id))


@main.route('/post/<int:post_id>/like', methods=['POST'])
@login_required
def like_post(post_id):
    with Session(engine) as session:
        # 检查用户是否已经点赞过该博文
        existing_like = session.exec(
            select(Like)
            .where(Like.user_id == current_user.id)
            .where(Like.post_id == post_id)
        ).first()

        if existing_like:
            # 如果已经点赞过，取消点赞
            session.delete(existing_like)
            session.commit()
            flash('已取消点赞！', 'info')
        else:
            # 如果未点赞过，添加点赞
            new_like = Like(user_id=current_user.id, post_id=post_id)
            session.add(new_like)
            session.commit()
            flash('点赞成功！', 'success')
        return redirect(url_for('main.view_post', post_id=post_id))


@app.errorhandler(404)
def page_not_found(error):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_server_error(error):
    return render_template('500.html', error=error), 500


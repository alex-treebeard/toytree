#!/usr/bin/env python

from __future__ import print_function, absolute_import

import re
import requests
from decimal import Decimal
from copy import deepcopy

from .ete3mini import TreeNode
from .TreeStyle import TreeStyle
from .Coords import Coords
from .Drawing import Drawing
from .utils import ToytreeError, TreeMod


class Toytree:
    def __init__(self, newick=None, ladderize=True, tree_format=0, **kwargs):

        # get the tree as a TreeNode object
        self._parse_to_TreeNode(newick, tree_format)

        # set tips order if fixing for multi-tree plotting (default None)
        self._fixed_order = None
        if kwargs.get("fixed_order"):
            self._set_fixed_order(kwargs["fixed_order"])

        # ladderize the tree unless user rotated nodes and wants it not.
        if ladderize and (not self._fixed_order):
            self.tree.ladderize()

        # Object for storing default plot settings or saved styles.
        # Calls several update functions when self.draw() to fit canvas.
        self._style = TreeStyle(tree_style='p')

        # Object for plot coordinates. Calls .update() whenever tree modified.
        self._coords = Coords(self)

        # Object for modifying trees beyond root, prune, drop
        self.mod = TreeMod(self)

    # --------------------------------------------------------------------
    # Class definitions 
    # --------------------------------------------------------------------    
    # ... could add __repr__, __iter__, __next__, but .tree has most already
    def __str__(self):
        """ return ascii tree ... (not sure whether to keep this) """
        return self.tree.__str__()

    def __len__(self):
        """ return len of Tree (ntips) """
        return len(self.tree)

    # --------------------------------------------------------------------
    # Loading Newick or ...
    # --------------------------------------------------------------------    
    def _parse_to_TreeNode(self, newick, tree_format):
        """
        Parse the newick string as either text, filepath or URL, and create an
        ete.TreeNode object as .tree. If no newick init an empty TreeNode.
        """
        if newick:
            # is newick a URL or string, path?
            if any((i in newick for i in ("http://", "https://"))):
                response = requests.get(newick)
                response.raise_for_status()
                newick = response.text.strip()
            # create .tree attribute as TreeNode
            self.tree = TreeNode(newick, format=tree_format)
        # otherwise make an empty TreeNode object
        else:
            self.tree = TreeNode()


    def _set_fixed_order(self, fixed_order):
        if fixed_order:
            if set(fixed_order) != set(self.tree.get_leaf_names()):
                raise ToytreeError(
                    "fixed_order must include same tipnames as tree")
            self._fixed_order = fixed_order

    # --------------------------------------------------------------------
    # properties are not changeable by the user
    # --------------------------------------------------------------------    
    @property
    def features(self):
        return self.tree.features

    @property
    def nnodes(self):
        return sum(1 for i in self.tree.traverse())

    @property
    def ntips(self):
        return sum(1 for i in self.tree.get_leaves())

    @property
    def newick(self, fmt=0):
        "Returns newick fmt=0 represenation of the tree in its current state."
        # checks one of root's children for features and extra feats.
        if self.tree.children:
            features = {"name", "dist", "support", "height", "idx"}
            testnode = self.tree.children[0]
            extrafeat = {i for i in testnode.features if i not in features}
            features.update(extrafeat)
            return self.tree.write(format=0)

    # --------------------------------------------------------------------
    # functions to return values from the ete3 .tree object --------------
    # --------------------------------------------------------------------
    def get_edge_lengths(self):
        """
        Returns edge length values from tree object in node plot order. To
        modify edge length values you must modify nodes in the .tree object
        directly. For example:

        for node in tree.tree.traverse():
            node.dist = 1.
        """
        return self.get_node_values('dist', True, True)


    def get_node_values(
        self, 
        feature=None, 
        show_root=False, 
        show_tips=False, 
        ):
        """
        Returns node values from tree object in node plot order. To modify
        values you must modify the .tree object directly by setting new
        'features'. For example

        for node in tree.tree.traverse():
            node.add_feature("PP", 100)

        By default node and tip values are hidden (set to "") so that they
        are not shown on the tree plot. To include values for these nodes
        use the 'show_root'=True, or 'show_tips'=True arguments.

        tree.get_node_values("support", True, True)

        """
        # access nodes in the order they will be plotted
        nodes = [
            self.tree.search_nodes(name=str(i))[0]
            for i in self.get_node_dict().values()
        ]

        # get features
        if feature:
            vals = [i.__getattribute__(feature)
                    if hasattr(i, feature) else "" for i in nodes]
        else:
            vals = [" " for i in nodes]

        # apply hiding rules
        if not show_root:
            vals = [i if not j.is_root() else "" for i, j in zip(vals, nodes)]
        if not show_tips:
            vals = [i if not j.is_leaf() else "" for i, j in zip(vals, nodes)]

        # convert float to ints for prettier printing unless all floats
        # raise exception and skip if there are true strings (names)
        try:
            if all([Decimal(str(i)) % 1 == 0 for i in vals if i]):
                vals = [int(i) if isinstance(i, float) else i for i in vals]
        except Exception:
            pass

        return vals


    def get_node_dict(self):
        """
        Return node labels as a dictionary mapping {idx: name} where
        idx is the order of nodes in 'preorder' traversal. Used internally
        by get_node_values() to return values in proper order.
        """
        names = {}
        idx = -1 + sum(1 for i in self.tree.traverse())

        # preorder: first parent and then children
        for node in self.tree.traverse("preorder"):
            if not node.is_leaf():
                if node.name:
                    names[idx] = node.name
                idx -= 1

        # names are in ladderized plotting order
        tiporder = self.tree.get_leaves()
        for node in tiporder:
            names[idx] = node.name
            idx -= 1
        return names


    def get_tip_labels(self):
        """
        returns tip labels in ladderized order from top to bottom on
        right-facing tree. Take care because this seems a bit odd for trees 
        that are facing down, i.e., here the the ladderized first node
        is on the right so names are returned right to left. 
        """
        if self._fixed_order:
            return self._fixed_order
        return self.tree.get_leaf_names()


    def is_rooted(self):
        """
        Returns False if the tree is unrooted.
        """
        if len(self.tree.children) > 2:
            return False
        return True


    def is_bifurcating(self, include_root=True):
        """
        Returns False if there is a polytomy in the tree, including if the tree
        is unrooted (basal polytomy), unless you use the include_root=False
        argument.
        """
        ctn1 = -1 + (2 * len(self))
        ctn2 = -2 + (2 * len(self))
        if self.is_rooted():
            return bool(ctn1 == sum(1 for i in self.tree.traverse()))
        if include_root:
            return bool(ctn2 == -1 + sum(1 for i in self.tree.traverse()))
        return bool(ctn2 == sum(1 for i in self.tree.traverse()))

    # --------------------------------------------------------------------
    # functions to modify the ete3 tree -
    # --------------------------------------------------------------------
    def copy(self):
        """ returns a deepcopy of the tree object"""
        return deepcopy(self)


    def prune(self, node_idx):
        """
        Returns a subtree pruned from the full tree at the selected
        node index. To find the appropriate index try using
        tre.draw(node_labels=True) and use the interactive hover
        feature, or tre.draw(node_labels='idx') to find the 'idx'
        value of the node on which you wish to prune the tree. If you
        simply want to drop tips from the tree rather than prune on an
        internal node, see the .drop_tip() function instead.

        ptre = tre.prune(15)
        """
        # make a deepcopy of the tree
        nself = self.copy()

        # ensure node_idx is int
        node = nself.tree.search_nodes(idx=int(node_idx))[0]
        nself.tree.prune(node)
        return nself


    def drop_tips(self, tips):
        """
        Returns a copy of the tree with the selected tips pruned from
        the tree. The entered value can be a name or list of names. To
        prune on an internal node to create a subtree of the existing
        tree see the .prune() function instead.

        ptre = tre.drop_tips(['a', 'b'])
        """
        # make a deepcopy of the tree
        nself = self.copy()

        # if tips is a string or Treenode
        if isinstance(tips, str):
            tips = [tips]
        elif isinstance(tips, TreeNode):
            tips = [tips.name]

        keeptips = [i for i in nself.get_tip_labels() if i not in tips]
        nself.tree.prune(keeptips)
        return nself


    def resolve_polytomy(
        self,
        default_dist=0.0,
        default_support=0.0,
        recursive=False):
        """
        Returns a copy of the tree with resolved polytomies.
        Does not transform tree in-place.
        """
        newtree = self.copy()
        newtree.tree.resolve_polytomy(
            default_dist=default_dist,
            default_support=default_support,
            recursive=recursive)
        return newtree


    def unroot(self):
        """
        Returns a copy of the tree unrooted. Does not transform tree in-place.
        """
        newtree = self.copy()
        newtree.tree.unroot()
        newtree.tree.ladderize()
        return newtree


    def root(self, outgroup=None, wildcard=None, regex=None):
        """
        Re-root a tree on a selected tip or group of tip names. Returns a 
        copy of the tree, the original tree object is not modified. 

        The new root can be selected by entering either a list of outgroup
        names, by entering a wildcard selector that matches their names, or
        using a regex command to match their names. For example, to root a tree
        on a clade that includes the samples "1-A" and "1-B" you can do any of
        the following:

        rtre = tre.root(outgroup=["1-A", "1-B"])
        rtre = tre.root(wildcard="1-")
        rtre = tre.root(regex="1-[A,B]")
        """

        # make a deepcopy of the tree
        nself = self.copy()

        # get names of outgroup/s using list, wildcard or regex
        og = outgroup
        if og:
            if isinstance(og, str):
                og = [og]
            notfound = [i for i in og if i not in nself.tree.get_leaf_names()]
            if any(notfound):
                raise Exception(
                    "Sample {} is not in the tree".format(notfound))
            outs = [i for i in nself.tree.get_leaf_names() if i in outgroup]

        elif regex:
            outs = [i.name for i in nself.tree.get_leaves()
                    if re.match(regex, i.name)]
            if not any(outs):
                raise Exception("No Samples matched the regular expression")

        elif wildcard:
            outs = [i.name for i in nself.tree.get_leaves()
                    if wildcard in i.name]
            if not any(outs):
                raise Exception("No Samples matched the wildcard")

        else:
            raise Exception(
                "must enter an outgroup, wildcard selector, or regex pattern")

        # get node to use for outgroup
        if len(outs) > 1:
            # check if they're monophyletic
            mbool, mtype, mnames = nself.tree.check_monophyly(
                outs, "name", ignore_missing=True)
            if not mbool:
                if mtype == "paraphyletic":
                    outs = [i.name for i in mnames]
                else:
                    raise Exception(
                        "Tips entered to root() cannot be paraphyletic")
            out = nself.tree.get_common_ancestor(outs)
        else:
            out = outs[0]

        # split root node if more than di- as this is the unrooted state
        if not nself.is_bifurcating():
            nself.tree.resolve_polytomy()

        # root the object with ete's translate
        nself.tree.set_outgroup(out)

        # get features
        testnode = nself.tree.get_leaves()[0]
        features = {"name", "dist", "support", "height"}
        extrafeat = {i for i in testnode.features if i not in features}
        features.update(extrafeat)

        # if there is a new node now, clean up its features
        nnode = [i for i in nself.tree.traverse() if not hasattr(i, "idx")]
        if nnode:
            # nnode is the node that was added
            # rnode is the location where it *should* have been added
            nnode = nnode[0]
            rnode = [i for i in nself.tree.children if i != out][0]

            # get idxs of existing nodes
            idxs = [int(i.idx) for i in nself.tree.traverse()
                    if hasattr(i, "idx")]

            # newnode is a tip
            if len(outs) == 1:
                nnode.name = str("rerooted")
                rnode.name = out
                rnode.add_feature("idx", max(idxs) + 1)
                rnode.dist *= 2
                sister = rnode.get_sisters()[0]
                sister.dist *= 2
                rnode.support = 100
                for feature in extrafeat:
                    nnode.add_feature(feature, getattr(rnode, feature))
                    rnode.del_feature(feature)

            # newnode is internal
            else:
                nnode.add_feature("idx", max(idxs) + 1)
                nnode.name = str("rerooted")
                nnode.dist *= 2
                sister = nnode.get_sisters()[0]
                sister.dist *= 2
                nnode.support = 100

        # store tree back into newick and reinit Toytree with new newick
        # if NHX format then preserve the NHX features.
        nself.tree.ladderize()
        return nself        

    # --------------------------------------------------------------------
    # Draw functions imported, but docstring here
    # --------------------------------------------------------------------
    def draw(
        self,
        tree_style=None,
        height=None,
        width=None,
        axes=None,        
        tip_labels=None,
        tip_labels_color=None,
        tip_labels_style=None,
        tip_labels_align=None,
        node_labels=None,
        node_labels_style=None,
        node_size=None,
        node_color=None,
        node_style=None,
        node_hover=None,
        edge_type=None,
        edge_style=None,
        edge_align_style=None,
        use_edge_lengths=None,
        orient=None,  
        scalebar=None,
        padding=None,
        # edge_width=None,
        # tip_labels_angle=None,  
        **kwargs,      
        ):
        """
        Plot a Toytree tree, returns a tuple of (Canvas, Axes).

        Parameters:
        -----------
        tree_style: str
            One of several preset styles for tree plotting. The default is 'n'
            (normal). Other options inlude 'c' (coalescent), 'd' (dark), ...
            This will set a default set of styling on top of which can be 
            combined with other plotting options that will override these 
            defaults.

        use_edge_lengths: bool
            Use edge lengths from .tree (.get_edge_lengths) else
            edges are set to length >=1 to make tree ultrametric.

        tip_labels: [True, False, list]
            If True then the tip labels from .tree are added to the plot.
            If False no tip labels are added. If a list of tip labels
            is provided it must be the same length as .get_tip_labels().

        tip_labels_color:
            ...

        tip_labels_style:
            ...

        tip_labels_align:
            ...

        node_labels: [True, False, list]
            If True then nodes are shown, if False then nodes are
            suppressed. If a list of node labels is provided it must be the
            same length and order as nodes in .get_node_dict(). Node labels
            can be generated in the proper order using the the
            .get_node_labels() function from a Toytree tree to draw info
            from the tree features.
            For example: node_labels=tree.get_node_labels("support").

        node_size: [int, list, None]
            If None then nodes are not shown, otherwise, if node_labels
            then node_size can be modified. If a list of node sizes is
            provided it must be the same length and order as nodes in
            .get_node_dict().

        node_color: [list]
            Use this argument only if you wish to set different colors for
            different nodes, in which case you must enter a list of colors
            as string names or HEX values the length and order of nodes in
            .get_node_dict(). If all nodes will be the same color then use
            instead the node_style dictionary:
            e.g., node_style={"fill": 'red'}

        node_style: [dict]

        ...

        node_hover: [True, False, list, dict]
            Default is True in which case node hover will show the node
            values. If False then no hover is shown. If a list or dict
            is provided (which should be in node order) then the values
            will be shown in order. If a dict then labels can be provided
            as well.
        """
        # store entered args
        canvas_args = {
            "height": height,
            "width": width,
        }
        axes_args = {
            "padding": padding,
            "scalebar": scalebar,
        }
        mark_args = {
            "orient": orient,
            "tip_labels": tip_labels,
            "tip_labels_color": tip_labels_color,
            "tip_labels_style": tip_labels_style,
            "tip_labels_align": tip_labels_align,
            "node_labels": node_labels,
            "node_labels_style": node_labels_style,
            "node_size": node_size,
            "node_color": node_color,
            "node_style": node_style,
            "node_hover": node_hover,
            "edge_type": edge_type,  
            "edge_style": edge_style,
            "edge_align_style": edge_align_style,
            "use_edge_lengths": use_edge_lengths,
            "tree_style": tree_style,
            # "edge_width": edge_width,  ## todo
            # "edge_color": edge_color,  ## todo
            # "tip_labels_angle": tip_labels_angle,
        } 

        # update tree style based on draw arguments
        ts = (tree_style if tree_style else 'normal')
        self._style = TreeStyle(tree_style=ts)
        self._style.update_mark(mark_args)
        self._style.update_axes(axes_args)
        self._style.update_canvas(canvas_args)

        # if user provided explicity axes already for the plot
        draw = Drawing(self)

        # and create drawing
        if kwargs.get("debug"):
            return draw

        canvas, axes = draw.update(axes=axes)
        return canvas, axes
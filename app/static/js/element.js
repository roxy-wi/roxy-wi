"use strict"; // silly safari

if (typeof elem == "undefined") {

    function elem(tagName, attributes, children, isHTML) {

        let parent;

        if (typeof tagName == "string") {
            parent = document.createElement(tagName);
        } else if (tagName instanceof HTMLElement) {
            parent = tagName;
        }

        // I'm tired of using null as the attributes, e.g.: elem("div", null, ["some", "elements"])
        // Wouldn't it be nice if I could just do: elem("div", ["some", "elements"])
        // attributes expects a plain object; we can use that to differentiate
        if (typeof attributes != "undefined" && ["undefined", "boolean"].includes(typeof children) && typeof isHTML == "undefined") {
            let attrType = typeof attributes;
            if (["string", "number"].includes(attrType)
                || (attrType == "object" && attributes instanceof Array)
                || (attrType == "object" && attributes instanceof HTMLElement) ) {
                isHTML = children;
                children = attributes;
                attributes = null;
            }
        }

        if (attributes) {

            for (let attribute in attributes) {

                if (attribute.startsWith("on")) {

                    let callback = attributes[attribute];

                    if (typeof callback == "string") {
                        parent.setAttribute(attribute, callback);
                    }
                    else if (typeof callback == "function") {

                        let eventMatch = attribute.match(/^on([a-zA-Z]+)/);
                        if (eventMatch) {
                            let event = eventMatch[1];
                            // TODO: make sure it's a valid event?
                            parent.addEventListener(event, callback);
                            parent.eventListeners = parent.eventListeners || {};
                            parent.eventListeners[event] = parent.eventListeners[event] || [];
                            parent.eventListeners[event].push(callback);
                        }

                    }

                } else {
                    parent.setAttribute(attribute, attributes[attribute]);
                }

            }

        }

        if (typeof children != "undefined" || children === 0) {
            elem.append(parent, children, isHTML);
        }

        return parent;
    };

    elem.append = function (parent, children, isHTML) {

        if (parent instanceof HTMLTextAreaElement || parent instanceof HTMLInputElement) {

            if (children instanceof Text || typeof children == "string" || typeof children == "number") {
                parent.value = children;
            }
            else if (children instanceof Array) {
                children.forEach(function (child) {
                    elem.append(parent, child);
                });
            }
            else if (typeof children == "function") {
                elem.append(parent, children());
            }

        } else {

            if (children instanceof HTMLElement || children instanceof Text) {
                parent.appendChild(children);
            }
            else if (typeof children == "string" || typeof children == "number") {
                if (isHTML) {
                    parent.innerHTML += children;
                } else {
                    parent.appendChild(document.createTextNode(children));
                }
            }
            else if (children instanceof Array) {
                children.forEach(function (child) {
                    elem.append(parent, child);
                });
            }
            else if (typeof children == "function") {
                elem.append(parent, children());
            }

        }
    };

    window.elem = elem;

} else {

    if (typeof elem == "function" && elem.hasOwnProperty("append")) {
        console.warn("elem() is already initialized.");
    } else {
        console.warn("The name \"elem\" is already in use by some other script.");
    }

}
